from pydantic import BaseModel,Field,ConfigDict,ValidationError
from decimal import Decimal
import json

class QoutePeopleInput(BaseModel):
    adults:int=Field(strict=True,ge=1,le=50)
    children:int = Field(strict=True,ge=0,le=50)


class KnowledgeSearchInput(BaseModel):
    model_config=ConfigDict(
        str_strip_whitespace=True,  #先去掉字符串两端空白，避免 "   " 被当作有效查询。
        extra="forbid"    #拒绝未定义的参数，避免模型随意增加字段。
    )

    query:str=Field(min_length=1,max_length=1000)
    top_k:int=Field(default=3,strict=True,ge=1,le=10)

#住宿单独的类，先定义，供总报价输入引用
class AccommodationItemInput(BaseModel):
    model_config=ConfigDict(
        str_strip_whitespace=True,
        extra="forbid"
    )

    room_type: str = Field(min_length=1, max_length=100)
    rooms: int = Field(strict=True, gt=0, le=50)
    nights: int = Field(strict=True, gt=0, le=30)
    room_night_price: Decimal | None = Field(
        default=None,
        ge=0,
        decimal_places=2,
        description="住宿参考费用，人民币元/间/晚",
    )


class CalculateQuoteInput(BaseModel):
    model_config=ConfigDict(
        str_strip_whitespace=True,
        extra="forbid"
    )

    adults:int=Field(strict=True,ge=1,le=50)
    children:int=Field(strict=True,ge=0,le=50)

    meal_price:Decimal | None=Field(   #可以是金额，也可以是“未提供”。
        default=None,
        ge=0,
        decimal_places=2,
        description="餐饮参考费用，人民币元/成人/整条线路"
    )

    room_items: list[AccommodationItemInput] | None = Field(
        default=None,
        description="住宿明细列表；未提供为None，明确不住宿为空列表，每项的房间数和晚数都必须大于0",
    )

    transport_price:Decimal | None=Field(   #可以是金额，也可以是“未提供”。
            default=None,
            ge=0,
            decimal_places=2,
            description="交通参考费用，人民币元/成人/整条线路"
        )

    guide_price:Decimal | None=Field(   #可以是金额，也可以是“未提供”。
            default=None,
            ge=0,
            decimal_places=2,
            description="导游参考费用，人民币元/成人/整条线路"
        )

    ticket_price:Decimal | None=Field(   #可以是金额，也可以是“未提供”。
            default=None,
            ge=0,
            decimal_places=2,
            description="门票参考费用，人民币元/成人/整条线路"
        )

    boat_price:Decimal | None=Field(   #可以是金额，也可以是“未提供”。
            default=None,
            ge=0,
            decimal_places=2,
            description="船票参考费用，人民币元/成人/整条线路"
        )    

    entertainment_price:Decimal | None=Field(   #可以是金额，也可以是“未提供”。
            default=None,
            ge=0,
            decimal_places=2,
            description="娱乐参考费用，人民币元/成人/整条线路"
        )

def tool_success(data):
    return{
        "ok":True,
        "data":data,
        "error":None
    }

def tool_faild(code,message):
    return{
        "ok":False,
        "data":None,
        "error":{"code":code,"message":message}
    }

def validate_search_input(raw):
    try:
        cheked=KnowledgeSearchInput.model_validate(raw)  #检查传入的字典。
    except ValidationError:
        return tool_faild(

            "INVALID_ARGUMENT",
            "检索参数不合法"
        )
    return tool_success(cheked.model_dump())  #传回字典格式的校验

def validate_quote_input(raw):
    try:
        cheked=CalculateQuoteInput.model_validate(raw)
    except ValidationError as error:
        for detail in error.errors():
            if (
                detail["loc"]
                and detail["loc"][-1] in ("rooms", "nights")
                and detail["type"] == "greater_than"
            ):
                return tool_faild(
                    "INVALID_ARGUMENT",
                    "请填写大于0的房间数和晚数；无需住宿时，请移除该条住宿明细",
                )
        return tool_faild(
            "INVALID_ARGUMENT",
            "校验不通过"
        )

    return tool_success(cheked.model_dump())


#工具列表
TOOL_VALIDATORS = {
    "knowledge_search": validate_search_input,
    "calculate_quote": validate_quote_input,
}

#验证工具
def validate_tool_input(tool_name,raw):
    if tool_name not in TOOL_VALIDATORS:
        return tool_faild("UNKNOWN_TOOL","未知工具错误")
    use_tool=TOOL_VALIDATORS[tool_name]
    result=use_tool(raw)

    return result

#提交内容

search_schema=CalculateQuoteInput.model_json_schema()



#工具契约
TOOL_CONTRACTS={
    "knowledge_search":{
        "description":"检索已有旅行资料，返回证据和来源，不生成最终答案。",
        "parameters":KnowledgeSearchInput.model_json_schema(),
    },
    "calculate_quote":{
        "description":"根据提供的单价进行计算，结果需要让员工进行确认",
        "parameters":CalculateQuoteInput.model_json_schema()
    }
}


def count_tool_call(tool_names):
    tool_counts={}
    for tool_name in tool_names:
        if tool_name in TOOL_VALIDATORS:
            tool_counts[tool_name]=tool_counts.get(tool_name,0)+1

    return tool_counts



#六项费用
def calculate_quote_amouts(data):
    price_fields = [
    "meal_price",
    "transport_price",
    "guide_price",
    "ticket_price",
    "boat_price",
    "entertainment_price",
    ]

    adult_base = Decimal("0.00")  #成人已知费用小计，开始为 0.00
    missing_items = []   #未提供价格的项目清单，开始是空列表

    for filed in price_fields:
        price=data[filed]

        if price is None:
            missing_items.append(filed)
        else:
            adult_base+=price

    return {
        "adult_base":adult_base,
        "missing_items":missing_items
    }

#住宿综合
def calculate_accommodation(data):
    rooms=data["rooms"]
    nights=data["nights"]
    room_price=data["room_night_price"]

    if rooms<=0 or nights<=0:
        raise ValueError("请填写大于0的房间数和晚数；无需住宿时，请移除该条住宿明细")
    if room_price is None:
        return None
    return room_price*rooms*nights




def summarize_accommodation(room_items):
    known_total=Decimal("0.00")
    missing_room_types=[]

    for item in room_items:
        amout=calculate_accommodation(item)
        if amout is None:
            missing_room_types.append(item["room_type"])
        else:
            known_total+=amout
    return {
        "known_total":known_total,
        "missing_rom_type":missing_room_types
    }


def calculate_quote_parts(raw):
    validation=validate_quote_input(raw)

    if not validation["ok"]:
        return validation

    data=validation["data"]

    one_peoplo_price=calculate_quote_amouts(data)
    accommodation=0
    
    if data["room_items"] is None:
        accommodation=None
    else:
        
        try:
            accommodation=summarize_accommodation(data["room_items"])
        except ValueError as error:
            return tool_faild("INVALID_ARGUMENT",str(error))
    
    return tool_success({
        "person_costs": one_peoplo_price,  #单人费用
        "accommodation": accommodation,   #住宿费用这组人计数的费用
        "requires_confirmation": True,   #提醒结果需要员工确认。
    })


raw = {
    "adults": 2,
    "children": 1,
    "meal_price": "50.00",
    "transport_price": "80.00",
    "guide_price": "20.00",
    "ticket_price": "0.00",
    "room_items": [
        {
            "room_type": "双床房",
            "rooms": 1,
            "nights": 2,
            "room_night_price": None,
        }
    ],
}






#检索工具低层
def knowledge_search(raw):
    validation=validate_search_input(raw)    #检验合法性

    if not validation["ok"]:
        return validation

    data=validation["data"]   #拿到query和top——k

    try:
        from app.rag_resources import get_rag_resources
        from app.retrieval import retrieve_evidence

        resources=get_rag_resources()  #拿到启动的环境准备

        evidence=retrieve_evidence(
            question=data["query"],
            model=resources["model"],
            collection=resources["collection"],
            reranker=resources["reranker"],
            n_results=max(7,data["top_k"]),  #防止重排不够
            top_k=data["top_k"]
        )
    except Exception:  #异常
        return tool_faild(
            "RETRIEVAL_FAILED",
            "资料检索暂时不可用，请稍后再试"
        )

    return tool_success({
        "evidence":evidence
    })






TOOL_HANDLERS={  #找到执行函数，真正进行计算。
    "calculate_quote":calculate_quote_parts,
    "knowledge_search":knowledge_search,
}

def calculate_tool_input(tool_name,raw):   #检查工具名是否支持，再找到对应函数，真正执行。
    if tool_name not in TOOL_HANDLERS:
        return tool_faild("UNKNOWN_TOOL","未知工具错误")
    use_tool=TOOL_HANDLERS[tool_name]
    result=use_tool(raw)

    return result


# raw：整份报价的原始输入，尚未校验。
# data：整份报价校验、转换后的字典，来自 model_dump()。
result = calculate_tool_input(
    "knowledge_search",
    {"query": "杭州适合晚上逛街的住宿区域", "top_k": 3},
)

print(result)