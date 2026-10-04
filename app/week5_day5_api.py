from fastapi import FastAPI,HTTPException,Depends
from pydantic import BaseModel,Field,ConfigDict
from examples.week5_day4_structured_output import(call_structured_model,StructuredAnswer)


app=FastAPI()
class ChatRequest(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True)
    question: str=Field(min_length=1,max_length=1000)

class ChatRestponse(BaseModel):
    data:StructuredAnswer | None
    error:str
    record:dict | None

class ErrorResponse(BaseModel):
    detail:str

@app.get("/health")
def health():
    return{"status":"ok"}

def get_model_caller():
    return call_structured_model
@app.post("/chat",response_model=ChatRestponse,responses={
        502: {
            "model": ErrorResponse,
            "description": "模型服务调用失败",
        }
    },)
def chat(
    request:ChatRequest,
    model_caller=Depends(get_model_caller)):

    result=model_caller(request.question)

    if result["error"]:
        raise HTTPException(
            status_code=502,
            detail=result["error"]
        )
    return result