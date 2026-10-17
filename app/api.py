from fastapi import FastAPI,HTTPException,Depends,Header,Path
from pydantic import BaseModel,Field,ConfigDict
from app.structured_output import StructuredAnswer
from app.conversation_store import( init_db,get_conversation,get_messages,save_turn,create_conversation_with_turn,delete_conversation)
from threading import Lock
from app.conversation_store import get_pending_question


init_db()
app = FastAPI()
MAX_HISTORY_TURNS=3
RAG_REQUEST_LOCK=Lock() #单进程锁

DEMO_TOKEN_USERS={
    "token_a":"user_a",
    "token_b":"user_b",
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

    rewrite_record: dict|None=None
    citations: list[dict]=Field(default_factory=list) #没提供使用自己的空列表。
    evidence:list[dict]=Field(default_factory=list)
    needs_clarification:bool=False

class ErrorResponse(BaseModel):
    detail:str


@app.get("/health")
def health():
    return{"status":"ok"}

def call_rag(question,history=None,*,pending_question=None):
    from app.rag_resources import get_rag_resources
    from app.rag_pipeline import run_rag

    if history is None:
        history=[]

    resources=get_rag_resources()

    return run_rag(
        question=question,
        history=history,
        model=resources["model"],
        collection=resources["collection"],
        reranker=resources["reranker"],
        pending_question=pending_question,
    )



def get_model_caller():
    return call_rag
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

    with RAG_REQUEST_LOCK:
        conversation_id=request.conversation_id
        history=[]
        pending_question=None

        
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
            history=history[-MAX_HISTORY_TURNS*2:]#倒数两个对话
            pending_question=get_pending_question(conversation_id)
            

        result=model_caller(request.question,
                            history=history,
                            pending_question=pending_question)

        # 出错时不保存消息，也不覆盖数据库中的追问状态
        if result["error"]:
            raise HTTPException(
                status_code=502,
                detail=result["error"]
            )

        if result["data"] is None:
            raise HTTPException(
                status_code=502,
                detail="未返回可用结果",
            )
        assistant_content=result["data"]["answer"]


        # 消息与新的追问状态在同一事务中保存
        if conversation_id is  None:
            conversation_id=create_conversation_with_turn(
                request.question[:30],
                current_user_id,
                request.question,
                result["data"]["answer"],
                pending_question=result["pending_question"],
            )
        else:
            save_turn(
                conversation_id,
                request.question,
                result["data"]["answer"],
                pending_question=result["pending_question"]
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
            detail="会话不存在"
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


@app.get("/conversations/{conversation_id}")
def get_conversation_detail(
    conversation_id:int =Path(ge=1),
    current_user_id:str=Depends(get_current_user_id)
):
    conversation=get_conversation(conversation_id)
    data={}
    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="会话不存在"
        )

    if conversation["owner_id"]!=current_user_id:
        raise HTTPException(
            status_code=403,
            detail="无权访问该会话"
        )

    messages=get_messages(conversation_id)
    data["conversation"]=conversation
    data["messages"]=messages

    return data