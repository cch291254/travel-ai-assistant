from pydantic import BaseModel


#/chat 返回给前端的回答结构
class StructuredAnswer(BaseModel):
    answer:str
    sources:list[str]
