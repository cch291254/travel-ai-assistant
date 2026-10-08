from fastapi import FastAPI,HTTPException,Depends,Header
from pydantic import BaseModel,Field,ConfigDict
from examples.week5_day4_structured_output import(call_structured_model,StructuredAnswer)
from app.conversation_store import( init_db,get_conversation,get_messages,save_turn,create_conversation_with_turn,delete_conversation)


init_db()
app = FastAPI()
MAX_HISTORY_TURNS=3

DEMO_TOKEN_USERS={
    "token_a":"user_a",
    "token_b":"user_b"
}
def get_current_user_id(
    authorization:str|None=Header(default=None)
):
    if authorization is None:
        raise HTTPException(
            status_code=401,
            detail="缺失访问令牌"
        )
    scheme,separator,token=authorization.partition(" ")

    if (
        scheme.lower()!="bearer"
        or separator==""
        or token not in DEMO_TOKEN_USERS
    ):
        raise HTTPException(
            status_code=401,
            detail="访问令牌无效"
        )

    return DEMO_TOKEN_USERS[token]


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
    current_user_id=Depends(get_current_user_id),
    model_caller=Depends(get_model_caller)):

    conversation_id=request.conversation_id
    history=[]

    
    if conversation_id is not None:
        conversation=get_conversation(conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404,detail="会话不存在")

        if conversation["owner_id"]!=current_user_id:
            raise HTTPException(
                status_code=403,
                detail="无权访问该对话"
            )
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
            current_user_id,
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


@app.delete("/conversations/{conversation_id}")
def remove_conversation(
    conversation_id:int,
    current_user_id=Depends(get_current_user_id)
):
    conversation=get_conversation(conversation_id)

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="会话不保存"
        )

    if conversation["owner_id"]!=current_user_id:
        raise HTTPException(
            status_code=403,
            detail="无权删除该对话"
        )

    delete_conversation(conversation_id)

    return {
        "status":"deleted",
        "conversation_id":conversation_id
    }