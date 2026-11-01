from fastapi import FastAPI,HTTPException,Depends,Header,Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel,Field,ConfigDict

from app.structured_output import StructuredAnswer
from app.conversation_store import( init_db,list_conversations, get_conversation,get_messages,save_turn,create_conversation_with_turn,delete_conversation)
from threading import Lock
from app.conversation_store import (get_pending_question,consume_daily_quota, get_draft,save_draft)

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

from typing import Literal
from datetime import datetime,timedelta,timezone
                    #日期和时间，一段时长，时区

from app.plan_store import (get_plan,list_plans,change_plan_status,delete_plan,copy_plan,create_plan,save_plan_version)
from app.draft_generator import draft_to_context,generate_draft


logger=logging.getLogger(__name__)

#后端的启动和关闭
@asynccontextmanager
async def lifespan(app):    #应用生命周期的写法，聊天接口保持原样。
    #在这里启动日志  
    setup_logging()    # 初始化本地日志
    setup_tracing()   
    try:
        from app.rag_resources import get_rag_resources
        get_rag_resources()
    except Exception:  #这里提前加载模型
        logger.exception("模型预加载失败，第一次检索时会重试")
    logger.info("后端启动，日志配置已就绪")

    try:
        yield     #开始处理
    finally:
        shutdown_tracing()  #发送追踪
        #这里关闭同步
        logger.info("后端已关闭")
    

init_db()
app = FastAPI(lifespan=lifespan)

MAX_BODY_BYTES=1024*1024  #限制请求体1m

#自动拒接过大请求
@app.middleware("http")
async def limit_body_size(request:Request,call_next):
    content_length=request.headers.get("content-length","")
    if content_length.isdigit() and int(content_length)>MAX_BODY_BYTES:
        return JSONResponse(status_code=413,content={"detail":"请求内容过大"})
    return await call_next(request)

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
DAILY_CHAT_LIMIT=50
CHINA_TZ=timezone(timedelta(hours=8))
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


#代替所以的conversation
def _get_owner_conversation(conversation_id,current_user_id):
    conversation=get_conversation(conversation_id)

    if conversation is None:
        raise HTTPException(status_code=404,detail="会话不存在")

    if conversation["owner_id"]!=current_user_id:
        raise HTTPException(
            status_code=403,
            detail="无权访问该对话"
        )

    return conversation

def _get_owner_plan(plan_id,current_user_id):
    plan=get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404,detail="方案不存在")

    if plan["owner_id"]!=current_user_id:
        raise HTTPException(status_code=403,detail="无权访问该方案")

    return plan


#每次调用模型前扣一次配额，用完返回 429
def _use_daily_quota(current_user_id):
    today=datetime.now(CHINA_TZ).date().isoformat()
    if not consume_daily_quota(current_user_id,today,DAILY_CHAT_LIMIT):
        raise HTTPException(status_code=429,detail="今日调用次数已用完")


def _generate_chat_draft(conversation_id,current_user_id):
    try:
        _use_daily_quota(current_user_id)
    except HTTPException as error:
        return{"generate_draft":None,"draft_error":error.detail}

    result=generate_draft(get_messages(conversation_id),conversation_id)
    return {"generated_draft":result["draft"],"draft_error":result["error"]}

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
    generated_draft:dict |None=None
    draft_error:str=""

class ErrorResponse(BaseModel):
    detail:str

class SaveDraftRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")  #不允许出现没有定义的字段
    draft:dict

class CreatePlanRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    title:str=Field(min_length=1)
    draft:dict
    conversation_id:int |  None=None

class SavePlanRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    draft:dict
    base_version:int=Field(ge=1)
    title:str|None=Field(default=None,min_length=1)

class ChangePlanStatusRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    status:Literal["draft","pending","confirmed"]  #限定只有那几个
    base_version:int=Field(ge=1)

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
    result["draft_requested"]=tool_result.get("draft_requested",False)

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
            conversation=_get_owner_conversation(conversation_id,current_user_id)

            history=get_messages(conversation_id)
            history=history[-MAX_HISTORY_TURNS*2:]#倒数两个对话
            draft=get_draft(conversation_id)
            if draft is not None:
                history=[{"role":"system","content":draft_to_context(draft)}]+history
            pending_question=get_pending_question(conversation_id)
            
        _use_daily_quota(current_user_id)

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
        if result.get("draft_requested"):
            result.update(_generate_chat_draft(conversation_id,current_user_id))
        return result

#看会话列表
@app.get("/conversations")
def read_conversation_list(
    current_user_id:str =Depends(get_current_user_id)
):
    return {"conversations":list_conversations(current_user_id)}


@app.delete("/conversations/{conversation_id}")
def remove_conversation(
    conversation_id:int,
    current_user_id=Depends(get_current_user_id)
):
    _get_owner_conversation(conversation_id,current_user_id)

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
    conversation=_get_owner_conversation(conversation_id,current_user_id)
    data={}
    

    messages=get_messages(conversation_id)
    data["conversation"]=conversation
    data["messages"]=messages

    return data

@app.get("/conversations/{conversation_id}/draft")
def read_draft(conversation_id:int=Path(ge=1),  #最小为1
    current_user_id: str =Depends(get_current_user_id)):
    _get_owner_conversation(conversation_id,current_user_id)

    return {"draft":get_draft(conversation_id)}


@app.put("/conversations/{conversation_id}/draft")
def write_draft(request:SaveDraftRequest,
                conversation_id:int =Path(ge=1),
                current_user_id:str =Depends(get_current_user_id)):
    _get_owner_conversation(conversation_id,current_user_id)
    save_draft(conversation_id,request.draft)
    return {"status":"saved"}


#读取全部聊天记录，整理成草案；只返回给页面，由页面保存
@app.post("/conversations/{conversation_id}/draft/generate")
def generate_conversation_draft(
    conversation_id:int=Path(ge=1),
    current_user_id:str=Depends(get_current_user_id),
):
    _get_owner_conversation(conversation_id,current_user_id)

    messages=get_messages(conversation_id)
    if not messages:
        raise HTTPException(status_code=422,detail="这个会话还没有可整理的内容")

    _use_daily_quota(current_user_id)

    result=generate_draft(messages,conversation_id)
    if result["error"]:
        raise HTTPException(status_code=502,detail=result["error"])

    return {"draft":result["draft"]}


#这是一组请求
@app.post("/plans")
def create_new_plan(request:CreatePlanRequest,
                    current_user_id:str =Depends(get_current_user_id)):
    if request.conversation_id is not None:
        _get_owner_conversation(request.conversation_id,current_user_id)
    plan_id=create_plan(current_user_id,request.title,request.draft,request.conversation_id)
    
    return {"plan_id":plan_id,"version":1}

#看哪些方案
@app.get("/plans")
def read_plan_list(
    current_user_id:str =Depends(get_current_user_id)
):
    return {"plans":list_plans(current_user_id)}

#看具体方案
@app.get("/plans/{plan_id}")
def read_plan(
    plan_id:int=Path(ge=1),
    current_user_id:str =Depends(get_current_user_id)
):
    plan=_get_owner_plan(plan_id,current_user_id)
    return plan


@app.delete("/plans/{plan_id}")
def remove_plan(plan_id:int=Path(ge=1),
    current_user_id:str =Depends(get_current_user_id)):
    _get_owner_plan(plan_id,current_user_id)
    delete_plan(plan_id)
    return {"status":"deleted","plan_id":plan_id}


@app.post("/plans/{plan_id}/copy")
def copy_existing_plan(plan_id:int=Path(ge=1),
    current_user_id:str =Depends(get_current_user_id)):
    _get_owner_plan(plan_id,current_user_id)
    new_plan_id=copy_plan(plan_id,current_user_id)
    return{"plan_id":new_plan_id,"version":1}


@app.put("/plans/{plan_id}")
def update_plan(request:SavePlanRequest,
        plan_id:int =Path(ge=1),
        current_user_id:str =Depends(get_current_user_id)):
    _get_owner_plan(plan_id,current_user_id)
    new_version=save_plan_version(plan_id,request.draft,request.base_version,current_user_id,request.title)
    if new_version is None:
        raise HTTPException(status_code=409,detail="方案已被修改，请刷新后重试")
    return {"plan_id":plan_id,"version":new_version}


@app.post("/plans/{plan_id}/status")
def update_plan_status(request:ChangePlanStatusRequest,
        plan_id:int =Path(ge=1),
        current_user_id:str =Depends(get_current_user_id)):
    _get_owner_plan(plan_id,current_user_id)
    result=change_plan_status(plan_id,request.base_version,request.status)
    if result["ok"] is False:
        if result["error"]=="version_conflict":
            raise HTTPException(status_code=409,detail="方案已被修改，请刷新后重试")
        if result["error"]=="invalid_transition":
            raise HTTPException(status_code=409,detail="当前状态不支持这个操作")
        if result["error"]=="missing_prices":
            raise HTTPException(status_code=422,detail="当前缺少这些价格："+"；".join(result["missing"]))

    return {"plan_id":plan_id,"status":result["status"]}