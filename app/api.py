from fastapi import FastAPI,HTTPException,Depends,Header,Path
from pydantic import BaseModel,Field,ConfigDict
from app.structured_output import StructuredAnswer
from app.conversation_store import( init_db,get_conversation,get_messages,save_turn,create_conversation_with_turn,delete_conversation)
from threading import Lock
from app.conversation_store import get_pending_question

import logging
from contextlib import asynccontextmanager   #定义应用启动和关闭
from app.logging_config import setup_logging,request_id_var  #导入日志模块

from fastapi import Request   #获取请求方法、路径
from time import perf_counter   #计算耗时
from uuid import uuid4   #独立编号
from app.tracing import setup_tracing,shutdown_tracing,get_tracing_client

import json

from app.tool_schemas import CalculateQuoteInput
from app.tools import calculate_quote_parts
from app.tool_results import tool_result_to_json


logger=logging.getLogger(__name__)

#后端的启动和关闭
@asynccontextmanager
async def lifespan(app):    #应用生命周期的写法，聊天接口保持原样。
    #在这里启动日志  
    setup_logging()    # 初始化本地日志
    setup_tracing()   
    logger.info("后端启动，日志配置已就绪")

    try:
        yield     #开始处理
    finally:
        shutdown_tracing()  #发送追踪
        #这里关闭同步
        logger.info("后端已关闭")
    

init_db()
app = FastAPI(lifespan=lifespan)

#记录每一次 HTTP 请求。
@app.middleware("http")    #middleware，在进行处理之前进行日志处理
async def log_request(request:Request,call_next):  #
    #编号处理
    request_id=uuid4().hex
    context_token=request_id_var.set(request_id)
    start_time=perf_counter()
    status_code=500 #出现的异常，按服务端错误记录

    try: #通过过滤获得request_id
        logger.info("请求开始 method=%s path=%s",request.method,request.url.path)

        #交给后面的接口处理，等待相应
        response=await call_next(request)
        status_code=response.status_code

        #编号放入请求头，统一相应
        response.headers["X-Request-ID"]=request_id
        return response

    except Exception:
        #这里记录异常
        logger.exception("请求发生异常 request_id=%s",request_id)
        raise

    finally:
        #记录耗时
        elapsed_ms=(perf_counter()-start_time)*1000
        logger.info(
            "请求结束 request_id=%s method=%s path=%s status=%s elapsed_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            status_code,
            elapsed_ms,
        )

        #恢复请求前的值
        request_id_var.reset(context_token)

MAX_HISTORY_TURNS=3
RAG_REQUEST_LOCK=Lock() #单进程锁

DEMO_TOKEN_USERS={
    "token_a":"user_a",
    "token_b":"user_b",
}

#这里进行初步的用户隔离
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

class ChatResponse(BaseModel):
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

#这里的请求是计算的
@app.post("/quotes/calculate")
def calculate_quote(
    request:CalculateQuoteInput,
    current_user_id:str=Depends(get_current_user_id)  #访问令牌校验
):
    result=calculate_quote_parts(request.model_dump())

    if not result["ok"]:
        raise HTTPException(
            status_code=422,
            detail=result["error"]["message"]
        )

    return json.loads(tool_result_to_json(result["data"]))

#工具的接口
def call_tool_chat(question,history=None,*,pending_question=None):
    from app.tool_calling import run_tool_chat

    if pending_question is not None:
        question=pending_question+"\n用户补充信息："+question

    client=get_tracing_client()

    if client is None:
        #未开启追踪，正常聊天
        tool_result=run_tool_chat(question,history=history)

    else:
        #开始聊天，关联本地日志
        with client.start_as_current_observation(
            as_type="span",
            name="tool-chat",
            metadata={"request_id":request_id_var.get()},
            input={
                "question_length":len(question),
                "history_messages":len(history or [])
            }
        ) as span:
            tool_result=run_tool_chat(question,history=history)

            #记录执行结果，
            span.update(output={
                "ok":not bool(tool_result["error"]),
                "answer_length":len(tool_result.get("answer") or "")
            })

            # 工具聊天返回错误时，在追踪中标为错误。
            if tool_result["error"]:
                span.update(
                    level="ERROR",
                    status_message="工具聊天处理失败",
                )

            #将langfuse 追踪编号写入本地
            logger.info(
                "聊天追踪 trace_id=%s",
                client.get_current_trace_id()
            )

    result={
        "data":None,
        "error":tool_result["error"],
        "record":None,
        "pending_question":None,
    }

    if tool_result["error"]:
        return result

    answer=tool_result["answer"]
    if not isinstance(answer,str) or not answer.strip():
        result["error"]="模型未返回有效回答"
        return result

    result["data"]={
        "answer":answer,
        "sources":tool_result.get("sources",[])
    }
    result["citations"]=tool_result.get("citations",[])
    result["evidence"]=tool_result.get("evidence",[])

    return result


#调用接口
def get_model_caller():
    return call_tool_chat
@app.post("/chat",response_model=ChatResponse,responses={
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