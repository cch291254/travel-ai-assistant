#工具入口
import logging
from decimal import Decimal

from pydantic import ValidationError

from app.tool_results import tool_failure, tool_success
from app.tool_schemas import CalculateQuoteInput, KnowledgeSearchInput,WebSearchInput,WebFetchInput

import os
from dotenv import load_dotenv
import requests



logger = logging.getLogger(__name__)
ACCOMMODATION_QUANTITY_MESSAGE = (
    "请填写大于0的房间数和晚数；无需住宿时，请移除该条住宿明细"
)


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

#搜索内部知识
def knowledge_search(raw):
    validation = validate_search_input(raw)
    if not validation["ok"]:
        return validation
    data = validation["data"]
    try:
        # 只有实际执行合法检索时，才导入并获取模型和向量库资源。
        from app.rag_resources import get_rag_resources
        from app.retrieval import retrieve_evidence

        resources = get_rag_resources()
        evidence = retrieve_evidence(
            question=data["query"],
            model=resources["model"],
            collection=resources["collection"],
            reranker=resources["reranker"],
            n_results=7,
            top_k=3,
        )
    except Exception:
        # 对外返回稳定提示；日志记录具体异常，便于排查导入、加载或检索问题。
        logger.exception("知识库检索工具执行失败")
        return tool_failure("RETRIEVAL_FAILED", "资料检索暂时不可用，请稍后再试")
    return tool_success({"evidence": evidence})

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
}

TOOL_HANDLERS = {
    "calculate_quote": calculate_quote_parts,     #计算价格
    "knowledge_search": knowledge_search,   #知识检索
    "web_search":web_search,
    "web_fetch": web_fetch,
}


def execute_tool(tool_name, raw):
    """只允许执行登记的工具；各工具在内部校验自己的输入。"""
    if not isinstance(tool_name, str) or tool_name not in TOOL_HANDLERS:
        return tool_failure("UNKNOWN_TOOL", "未知工具错误")
    handler = TOOL_HANDLERS[tool_name]
    return handler(raw)


def compact_tool_schema(value):
    # 只精简模型看到的说明，不修改 Pydantic 的校验规则。
    if isinstance(value, dict):
        return {
            key: compact_tool_schema(item)
            for key, item in value.items()
            if key not in {"title", "default", "pattern"}
        }

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
