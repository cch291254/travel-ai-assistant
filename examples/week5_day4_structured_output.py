import json
from pydantic import BaseModel,ValidationError
from examples.week5_day3_my_client import call_model

class StructuredAnswer(BaseModel):
    answer:str
    sources:list[str]


def parse_structured_answer(raw_text):
    result={"data":None,"error":""}
    try:
        data=json.loads(raw_text)
        checked=StructuredAnswer.model_validate(data)
        result["data"]=checked.model_dump()
    except json.JSONDecodeError as error:
        result["error"]=str(error)
    except ValidationError as error:
        result["error"]=str(error)
    return result

system_prompt = (
    '你是一名旅行助手。只返回一个JSON对象，不要附加说明或Markdown代码块。'
    '必须包含answer和sources：answer是字符串，sources是字符串列表。'
    '没有可靠来源时，sources返回空列表，不要编造来源。'
    '输出示例：{"answer":"简短回答","sources":[]}。'
)
def call_structured_model(question):
    model_result=call_model(question,system_prompt=system_prompt,json_mode=True)

    if model_result["error"]:
        return{
            "data":None,
            "error":model_result["error"],
            "record":model_result["record"]}
    parse_result=parse_structured_answer(model_result["answer"])
    parse_result["record"]=model_result["record"]
    return parse_result
if __name__ == "__main__":
    
    result = call_structured_model("推荐一个杭州景点")
    print(result)


