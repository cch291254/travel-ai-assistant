#工具入口
import logging
from decimal import Decimal

from pydantic import ValidationError
from contextvars import ContextVar

from app.tool_results import tool_failure, tool_success
from app.tool_schemas import CalculateQuoteInput,SaveToDraftInput, KnowledgeSearchInput,WebSearchInput,WebFetchInput

import os
from dotenv import load_dotenv
import requests



logger = logging.getLogger(__name__)
ACCOMMODATION_QUANTITY_MESSAGE = (
    "请填写大于0的房间数和晚数；无需住宿时，请移除该条住宿明细"
)

search_state_var=ContextVar("search_state",default=None)
owner_id_var=ContextVar("owner_id",default=None)

def validate_search_input(raw):
    try:
        checked = KnowledgeSearchInput.model_validate(raw)
    except ValidationError:
        return tool_failure("INVALID_ARGUMENT", "检索参数不合法")
    return tool_success(checked.model_dump())


def validate_quote_input(raw):
    try:
        checked = CalculateQuoteInput.model_validate(raw)
    except ValidationError as error:
        for detail in error.errors():
            if (
                detail["loc"]
                and detail["loc"][-1] in ("rooms", "nights")
                and detail["type"] == "greater_than"
            ):
                return tool_failure("INVALID_ARGUMENT", ACCOMMODATION_QUANTITY_MESSAGE)
        return tool_failure("INVALID_ARGUMENT", "校验不通过")
    return tool_success(checked.model_dump())

def validate_web_search_input(raw):
    try:
        checked=WebSearchInput.model_validate(raw)
    except ValidationError:
        return tool_failure("INVALID_ARGUMENT","校验不通过")
    return tool_success(checked.model_dump())

def validate_web_fetch_input(raw):
    try:
        checked=WebFetchInput.model_validate(raw)
    except ValidationError:
        return tool_failure("INVALID_ARGUMENT","网页抓取参数不合法")
    return tool_success(checked.model_dump(mode="json"))  #额外注意抓取形式




def calculate_quote_amounts(data):
    """成人单人已知费用；未提供项目不是必须补齐的费用清单。"""
    price_fields = (
        "meal_price", "transport_price", "guide_price",
        "ticket_price", "boat_price", "entertainment_price",
    )
    known_total = Decimal("0.00")
    missing_items = []
    for field in price_fields:
        price = data[field]
        if price is None:
            missing_items.append(field)
        else:
            known_total += price
    return {"known_total": known_total, "missing_items": missing_items}


def calculate_accommodation(room_data):
    """一条房型明细的整组住宿费用，不按成人或儿童分摊。"""
    rooms = room_data["rooms"]
    nights = room_data["nights"]
    room_price = room_data["room_night_price"]
    if rooms <= 0 or nights <= 0:
        raise ValueError(ACCOMMODATION_QUANTITY_MESSAGE)
    if room_price is None:
        return None
    return room_price * rooms * nights


def summarize_accommodation(room_items):
    known_total = Decimal("0.00")
    missing_room_types = []
    for room_data in room_items:
        amount = calculate_accommodation(room_data)
        if amount is None:
            missing_room_types.append(room_data["room_type"])
        else:
            known_total += amount
    return {"known_total": known_total,
            "missing_room_types": missing_room_types}

#计算
def calculate_quote_parts(raw):
    """分别计算成人、儿童已知费用，再加上一次整组住宿费用。"""
    validation = validate_quote_input(raw)
    if not validation["ok"]:
        return validation
    data = validation["data"]
    adult_costs = calculate_quote_amounts(data)

    person_costs = {
        "adult_base": adult_costs["known_total"],
        "missing_items": adult_costs["missing_items"],
    }

    #计算房间
    if data["room_items"] is None:
        accommodation = None
    else:
        try:
            accommodation = summarize_accommodation(data["room_items"])
        except ValueError as error:
            return tool_failure("INVALID_ARGUMENT", str(error))

    #计算成人
    adult_known_total = person_costs["adult_base"] * data["adults"]

    #计算儿童，共用计算逻辑
    child_costs = None
    child_known_total = None

    if data["children"] == 0:
        child_known_total = Decimal("0.00")
    elif data["child_prices"] is not None:
        child_amounts = calculate_quote_amounts(data["child_prices"])

        child_costs = {
            "child_base": child_amounts["known_total"],
            "missing_items": child_amounts["missing_items"],
        }
        child_known_total = child_costs["child_base"] * data["children"]

    known_total = adult_known_total

    if child_known_total is not None:
        known_total += child_known_total

    if accommodation is not None:
        known_total += accommodation["known_total"]

    return tool_success({
        "person_costs": person_costs,    #单人六项价格
        "child_costs":child_costs,     #儿童六项价格
        "adult_known_total": adult_known_total,
        "child_known_total": child_known_total,
        "accommodation": accommodation,
        "known_total": known_total,
        "requires_confirmation": True,
    })


#把重写的用量记成一次模型调用，评测报告才能算进总成本
def trace_rewrite_usage(record):
    from app.tracing import get_tracing_client

    client=get_tracing_client()
    if client is None or record is None or record["总tokens"] is None:
        return
    with client.start_as_current_observation(
        as_type="generation",
        name="model-call",
        model=record["模型名"],
        metadata={"step":"rewrite"},
    ) as generation:
        generation.update(usage_details={
            "input":record["输入tokens"],
            "output":record["输出tokens"],
            "total":record["总tokens"],
        })


#重写
def plan_search(query,history=None):
    from app.query_rewriter import rewrite_retrieval_question

    plan={"queries":[query],"where":None,"clarification":""}
    result=rewrite_retrieval_question(query,history=history)
    trace_rewrite_usage(result.get("record"))
    if result["error"]:
        logger.warning("重写调用失败")
        return plan
    if result["needs_clarification"]:
        plan["clarification"]=result["clarification_question"]
        return plan
    retrieve_questions=[result["answer"].strip()]
    for sub_question in result["sub_questions"]:
        if sub_question not in retrieve_questions:
            retrieve_questions.append(sub_question)
    plan["queries"]=retrieve_questions
    if result["target_source_ids"]:
        plan["where"]={"source_id":{"$in":result["target_source_ids"]}}
    return plan

#判断第一次检索,是就重写
def get_search_plan(query):
    state=search_state_var.get()   #记录history,searched,where
    if state is None:
        return {"queries":[query],"where":None,"clarification":""}
    if state["searched"]:
        return {"queries":[query],"where":state["where"],"clarification":""}
    #能走到这里就是第一次检索
    state["searched"]=True
    plan=plan_search(query,state["history"])
    state["where"]=plan["where"]
    return plan

#子问题检索
def retrieve_routes(queries,resources,where=None):
    from app.retrieval import retrieve_evidence

    evidence=[]
    seen_chunk_ids=set()
    for query in queries:
        result=retrieve_evidence(query,
                                resources["model"],
                                resources["collection"],
                                resources["reranker"],where=where,n_results=7,top_k=3)
        for item in result:
            if item["chunk_id"] not in seen_chunk_ids:
                seen_chunk_ids.add(item["chunk_id"])
                evidence.append(item)

    return evidence



#搜索内部知识
def knowledge_search(raw):
    validation = validate_search_input(raw)
    if not validation["ok"]:
        return validation
    data = validation["data"]
    try:
        # 只有实际执行合法检索时，才导入并获取模型和向量库资源。
        from app.rag_resources import get_rag_resources

        plan=get_search_plan(data["query"])
        if plan["clarification"]:
            return tool_success({"clarification":plan["clarification"]})
        resources=get_rag_resources()
        evidence=retrieve_routes(plan["queries"],resources,where=plan["where"])
        if plan["where"] is not None and len(evidence)<2:
            evidence=retrieve_routes(plan["queries"],resources)   #资料不足，全量检索

    except Exception:
        # 对外返回稳定提示；日志记录具体异常，便于排查导入、加载或检索问题。
        logger.exception("知识库检索工具执行失败")
        return tool_failure("RETRIEVAL_FAILED", "资料检索暂时不可用，请稍后再试")
    return tool_success({"evidence": evidence})

#检索已确认方案
def confirmed_plan_search(raw):
    validation=validate_search_input(raw)
    if not validation["ok"]:
        return validation
    owner_id=owner_id_var.get()
    if owner_id is None:
        return tool_failure("NO_OWNER","无法确认员工身份不能查询方案")

    try:
        from app.plan_index import get_plan_collection
        from app.rag_resources import get_rag_resources
        resources={
            **get_rag_resources(),
            "collection":get_plan_collection()
        }

        evidence=retrieve_routes(
            [validation["data"]["query"]],
            resources,
            where={"owner_id":owner_id}
        )

    except Exception:
        logger.exception("方案检索工具执行失败")
        return tool_failure("RETRIEVAL_FAILED","方案检索暂时不可用，请稍后重试")

    return tool_success({"evidence":evidence})



#网络搜索
def web_search(raw):
    validation=validate_web_search_input(raw)
    if not validation["ok"]:
        return validation
    data=validation["data"]
    try:
        load_dotenv()
        api_key=os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            return tool_failure(
                "CONFIG_ERROR",
                "未配置api"   #没有配置
            )
    except Exception:   #没有找到
        return tool_failure("CONFIG_ERROR","读取搜索服务配置失败")
    headers={
        "Authorization":f"Bearer {api_key}",
        "Content-Type":"application/json"
    }
    payload={
        "query":data["query"],
        "count":data["count"]
    }

    #尝试请求
    try:
        response=requests.post(
            "https://api.deepseek.com/v1/tools/search",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()  #拿到请求比如200

    except requests.exceptions.Timeout:
        return tool_failure("SEARCH_TIMEOUT","网络搜索请求超时")
    except requests.exceptions.RequestException:
        logger.exception("网络搜索请求失败")
        return tool_failure("SEARCH_FAILED","网络搜索服务请求失败")

    #拿到答案
    try:
        search_data=response.json()  #取结果
    except ValueError:
        logger.exception("搜索内容无法解析为json")
        return tool_failure("SEARCH_BAD_RESPONSE","搜索服务返回格式异常")

    if not isinstance(search_data,dict):
        return tool_failure("SEARCH_BAD_RESPONSE","搜索服务返回格式异常")
    results=search_data.get("results")

    if not isinstance(results,list):
        return tool_failure("SEARCH_BAD_RESPONSE","搜索服务返回格式异常")

    return tool_success({"results":results})

#抓取工具
def web_fetch(raw):
    Validation=validate_web_fetch_input(raw)

    if not Validation["ok"]:
        return Validation
    data=Validation["data"]
    try:
        load_dotenv()
        api_key=os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            return tool_failure(
                "CONFIG_ERROR",
                "未配置api"
            )
    except Exception:
        return tool_failure(
            "CONFIG_ERROR",
            "读取抓取服务失败"
        )

    headers={
        "Authorization":f"Bearer {api_key}",
        "Content-Type": "application/json"   #告诉服务器正文为json格式
    }

    payload={
        "url":data["url"]
    }

    try:
        response=requests.post(
            "https://api.deepseek.com/v1/tools/fetch",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()

    except requests.exceptions.Timeout:
            return tool_failure("FETCH_TIMEOUT","网络抓取请求超时")
    except requests.exceptions.RequestException:
        logger.exception("网络抓取请求失败")
        return tool_failure("FETCH_FAILED","网络抓取服务请求失败")

    try:
        fetch_result=response.json()
    except ValueError:
        return tool_failure("FETCH_BAD_RESPONSE","抓取服务返回格式异常")

    if not isinstance(fetch_result,dict):
        return tool_failure("FETCH_BAD_RESPONSE","抓取服务返回格式异常")
    title=fetch_result.get("title","")
    if not isinstance(title,str):
        return tool_failure("FETCH_BAD_RESPONSE","抓取服务返回格式异常")
    content=fetch_result.get("content")
    if not isinstance(content,str) or not content.strip():
        return tool_failure("FETCH_BAD_RESPONSE","抓取服务返回格式异常")
    return tool_success({
        "url":data["url"],
        "title":title,
        "content":content,
    })


def save_to_draft(raw):
    return tool_success({"message":"已记录，系统会在本轮回答后整理草案。请简短告诉员工去右侧核对。"})


# 内部工具说明。以后对接模型时仍需转换成所用 API 的工具格式。
TOOL_CONTRACTS = {
    "knowledge_search": {
                "description": (
            "检索本项目内部旅行资料，当前资料主要覆盖杭州及周边的"
            "景点、住宿区域、旅行产品和业务规则。"
            "返回证据和来源，不生成最终答案。"
            "其他城市的公开住宿推荐优先使用web_search。"
        ),
        "parameters": KnowledgeSearchInput.model_json_schema(),
    },
    "calculate_quote": {
        "description": (
            "根据员工提供的成人、儿童单人价格及人数，分别计算已知费用，"
    "并加上一次整组住宿费用，返回整组已知费用合计。"
    "价格是人民币、单人整条线路的参考费用；未提供的留空，0表示明确为零。"
    "未提供价格不代表免费，儿童不自动套用成人价格，结果需员工确认。"
        ),
        "parameters": CalculateQuoteInput.model_json_schema(),
    },
    "web_search":{
        "description":"网络搜索公开网页，返回标题、链接和摘要，不生成最终答案。",
        "parameters":WebSearchInput.model_json_schema()
    },
    "web_fetch": {
    "description": "获取指定公开网页的标题和正文，不生成最终答案，不保证网页可访问。",
    "parameters": WebFetchInput.model_json_schema(),
    },
    "save_to_draft": {
        "description": (
            "把本次对话整理成方案草案。只有员工明确要求保存、整理或生成草案时才调用；"
            "询问问题、讨论假设或只是提到草案时不要调用。"
        ),
        "parameters": SaveToDraftInput.model_json_schema(),
    },
        "confirmed_plan_search": {
        "description": (
            "检索当前员工已确认的历史线路方案。只有员工问到以前做过的方案、"
            "想参考旧行程或旧报价时才调用；方案价格只代表当时那一单，不是业务规则。"
        ),
        "parameters": KnowledgeSearchInput.model_json_schema(),
    },
    }


TOOL_HANDLERS = {
    "calculate_quote": calculate_quote_parts,     #计算价格
    "knowledge_search": knowledge_search,   #知识检索
    "web_search":web_search,
    "web_fetch": web_fetch,
    "save_to_draft":save_to_draft,
    "confirmed_plan_search": confirmed_plan_search,
}


def execute_tool(tool_name, raw):
    """只允许执行登记的工具；各工具在内部校验自己的输入。"""
    if not isinstance(tool_name, str) or tool_name not in TOOL_HANDLERS:
        return tool_failure("UNKNOWN_TOOL", "未知工具错误")
    handler = TOOL_HANDLERS[tool_name]
    return handler(raw)


COMPACT_SCHEMA_KEYS = {
    "title", "default", "pattern",
    "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum",
}


def compact_tool_schema(value):
    # 只精简模型看到的说明，不修改 Pydantic 的校验规则。
    if isinstance(value, dict):
        compact = {
            key: compact_tool_schema(item)
            for key, item in value.items()
            if key not in COMPACT_SCHEMA_KEYS
        }
        # 金额校验时接受数字和字符串，模型只需知道填数字。
        if any(item.get("type") == "number" for item in compact.get("anyOf", [])):
            del compact["anyOf"]
            compact["type"] = "number"
        return compact

    if isinstance(value, list):
        return [compact_tool_schema(item) for item in value]

    return value



#函数提交
def build_model_tools():
    tools=[]

    for tool_name,contract in TOOL_CONTRACTS.items():
        tools.append({
            "type":"function",
            "function":{   #函数
                "name":tool_name,
                "description":contract["description"],
                "parameters": compact_tool_schema(contract["parameters"])
            }
        })
    return tools