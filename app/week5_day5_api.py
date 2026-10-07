from fastapi import FastAPI,HTTPException,Depends
from pydantic import BaseModel,Field,ConfigDict
from examples.week5_day4_structured_output import(call_structured_model,StructuredAnswer)
from app.conversation_store import( get_conversation,get_messages,save_turn,create_conversation_with_turn)


MAX_HISTORY_TURNS=3
app=FastAPI()
class ChatRequest(BaseModel):
    model_config=ConfigDict(str_strip_whitespace=True)
    question: str=Field(min_length=1,max_length=1000)
    conversation_id:int | None=Field(default=None,ge=1)

class ChatRestponse(BaseModel):
    conversation_id:int|None=None
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

    conversation_id=request.conversation_id
    history=[]

    if conversation_id is not None:
        conversation=get_conversation(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404,detail="会话不存在")

        history=get_messages(conversation_id)

        max_history_messages=MAX_HISTORY_TURNS*2
        history=history[-max_history_messages:]

    result=model_caller(request.question,history=history)

    if result["error"]:
        raise HTTPException(
            status_code=502,
            detail=result["error"]
        )
    if conversation_id is  None:
        conversation_id=create_conversation_with_turn(
            request.question[:30],
            "user_a",
            request.question,
            result["data"]["answer"]
        )
    else:
        save_turn(
            conversation_id,
            request.question,
            result["data"]["answer"]
        )
    result["conversation_id"]=conversation_id
    return result