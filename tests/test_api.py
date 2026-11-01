from unittest.mock import patch,Mock

import pytest
from fastapi.testclient import TestClient

import app.conversation_store as store
import requests
from app.workspace_plan import empty_draft
from app.draft_generator import ExtractedDraft, to_draft
from app.tools import search_state_var
from app.tool_calling import run_tool_chat

with patch.object(store, "init_db"):#防止提前初始化数据库
    import app.api as api #正常导入api,让init——db储存库临时替换


client=TestClient(api.app)
client.headers.update({
    "Authorization":"Bearer token_a"
})

@pytest.fixture(autouse=True)#每条测试自动使用临时数据库
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(
        store,
        "DB_PATH",
        tmp_path/"test_conversation.db"
    )  
    store.init_db()
    #函数自动模拟连接测试数据库

     # 测试必须自己提供模拟 RAG，不允许意外调用真实模型
    def forbig_real_rag(*ARGS,**kwargs):#禁止调用函数
        raise AssertionError("测试未设置模拟 RAG，禁止调用真实模型")

    monkeypatch.setitem(
        api.app.dependency_overrides, #FastAPI 提供的“依赖替换字典”
        api.get_model_caller,  #指定
        lambda:forbig_real_rag,  #替换
    )





def test_heakth():
    response=client.get("/health")

    assert response.status_code==200
    assert response.json()=={"status":"ok"}

def test_not_exist():
    response=client.get("/not_exist")

    assert response.status_code==404
    assert response.json()=={"detail":"Not Found"}


def test_chat_success(monkeypatch):
    model_calls=[]
    created_turns=[]
    def fake_call_model(question, history=None, *, pending_question=None):
        model_calls.append({
        "question": question,
        "history": history,
    })

        return {
            "data": {
                "answer": "推荐西湖",
                "sources": [],
            },
            "error": "",
            "record": {"状态码": 200},
            "pending_question": None,
        }
    def fake_create_conversation_with_turn(
        title,
    owner_id,
    user_content,
    assistant_content,
    *,
    pending_question=None,
    ):
        created_turns.append({
            "title":title,
            "owner_id":owner_id,
            "user_content":user_content,
            "assistant_content":assistant_content
        })
        return 100
    monkeypatch.setattr(
        api,
        "create_conversation_with_turn",
        fake_create_conversation_with_turn
    )
    def fake_get_model_caller():
        return fake_call_model

    monkeypatch.setitem(
    api.app.dependency_overrides,
    api.get_model_caller,
    fake_get_model_caller
)
    response=client.post(
        "/chat",
        json={"question":"推荐杭州景点"},
    )
    result=response.json()

    assert result["data"]["answer"]=="推荐西湖"
    assert result["data"]["sources"]==[]
    assert result["error"]==""
    assert result["record"]["状态码"]==200
    assert response.status_code == 200
    assert result["conversation_id"] == 100

    assert model_calls == [{
    "question": "推荐杭州景点",
    "history": []
}]

    assert created_turns == [{
    "title": "推荐杭州景点",
    "owner_id": "user_a",
    "user_content": "推荐杭州景点",
    "assistant_content": "推荐西湖"
}]

def test_chat_empty_question(monkeypatch):
    calls = []
    def fake_call_model(question, history=None, *, pending_question=None):
        calls.append(question)
        return{
            "data":{
                "answer":"推荐西湖",
                "sources":[],
            },
            "error":"",
            "record":{"状态码":200},
            "pending_question": None,
        }
    def fake_get_model_caller():
        return fake_call_model

    monkeypatch.setitem(
        api.app.dependency_overrides,
        api.get_model_caller,
        fake_get_model_caller,
    )
    response=client.post(
        "/chat",
        json={"question":""},
    )
    result=response.json()

    assert response.status_code == 422
    assert calls==[]

def test_chat_whitespace_question(monkeypatch):
    calls = []
    def fake_call_model(question, history=None, *, pending_question=None):
        calls.append(question)
        return{
            "data":{
                "answer":"推荐西湖",
                "sources":[],
            },
            "error":"",
            "record":{"状态码":200},
        }
    def fake_get_model_caller():
        return fake_call_model

    monkeypatch.setitem(
        api.app.dependency_overrides,
        api.get_model_caller,
        fake_get_model_caller,
    )
    response=client.post(
        "/chat",
        json={"question":"  "},
    )
    result=response.json()

    assert response.status_code == 422
    assert calls==[]

def test_chat_model_error(monkeypatch):
    def fake_call_model(question, history=None, *, pending_question=None):
        return{
            "data":None,
            "error":"模拟模型服务失败",
            "record":None,
        }
    def fake_get_model_caller():
        return fake_call_model
    
    monkeypatch.setitem(
        api.app.dependency_overrides,
        api.get_model_caller,
        fake_get_model_caller,
    )

    response=client.post(
        "/chat",
        json={"question":"推荐杭州景点"}
    )
    result=response.json()

    assert response.status_code==502
    assert result=={"detail":"模拟模型服务失败"}

def test_chat_model_timeout(monkeypatch):
    def fake_call_model(question, history=None, *, pending_question=None):
        return{
            "data":None,
            "error":"模拟模型调用超时",
            "record":None,
        }
    def fake_get_model_caller():
        return fake_call_model
    
    monkeypatch.setitem(
        api.app.dependency_overrides,
        api.get_model_caller,
        fake_get_model_caller,
    )

    response=client.post(
        "/chat",
        json={"question":"推荐杭州景点"}
    )
    result=response.json()

    assert response.status_code==502
    assert result=={"detail":"模拟模型调用超时"}

def test_chat_missing_data(monkeypatch):
    def fake_rag(question, history=None, *, pending_question=None):
        return {
            "data": None,
            "error": "",
            "record": None,
            "pending_question": None,
        }

    monkeypatch.setitem(
        api.app.dependency_overrides,
        api.get_model_caller,
        lambda: fake_rag,
    )

    response = client.post(
        "/chat",
        json={"question": "推荐杭州景点"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "未返回可用结果"}


def test_chat_existing_conversation(monkeypatch, isolated_db):
    conversation_id = store.create_conversation_with_turn(
    "杭州旅行",
    "user_a",
    "我想去杭州玩两天",
    "可以安排西湖和灵隐寺"
    )
    model_calls = []

    def fake_call_model(question, history=None, *, pending_question=None):
        model_calls.append({
            "question": question,
            "history": history,
        })

        return {
            "data": {
                "answer": "下雨时可以安排博物馆",
                "sources": []
            },
            "error": "",
            "record": {"状态码": 200},
            "pending_question": None,

        }

    def fake_get_model_caller():
        return fake_call_model

    monkeypatch.setitem(
        api.app.dependency_overrides,
        api.get_model_caller,
        fake_get_model_caller
    )
    response=client.post(
        "/chat",
        json={
            "question":"如果下雨怎么办？",
            "conversation_id":conversation_id
        }
    )
    result=response.json()
    messages = store.get_messages(conversation_id)

    assert response.status_code == 200
    assert result["conversation_id"] == conversation_id
    assert result["data"]["answer"] == "下雨时可以安排博物馆"
    assert model_calls == [{
    "question": "如果下雨怎么办？",
    "history": [
        {
            "role": "user",
            "content": "我想去杭州玩两天"
        },
        {
            "role": "assistant",
            "content": "可以安排西湖和灵隐寺"
        }
    ]
}]        
    assert messages == [
    {
        "role": "user",
        "content": "我想去杭州玩两天"
    },
    {
        "role": "assistant",
        "content": "可以安排西湖和灵隐寺"
    },
    {
        "role": "user",
        "content": "如果下雨怎么办？"
    },
    {
        "role": "assistant",
        "content": "下雨时可以安排博物馆"
    }
]
def test_chat_conversation_not_found(monkeypatch, isolated_db):
    model_calls = []

    def fake_call_model(question, history=None, *, pending_question=None):
        model_calls.append({
            "question": question,
            "history": history
        })

        return {
            "data": {
                "answer": "不应该执行到这里",
                "sources": []
            },
            "error": "",
            "record": {"状态码": 200},
            "pending_question": None,

        }

    def fake_get_model_caller():
        return fake_call_model

    monkeypatch.setitem(
        api.app.dependency_overrides,
        api.get_model_caller,
        fake_get_model_caller
    )

    response = client.post(
        "/chat",
        json={
            "question": "继续对话",
            "conversation_id": 999999
        }
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "会话不存在"
    }
    assert model_calls == []

def test_chat_history_limit(monkeypatch, isolated_db):
    conversation_id = store.create_conversation_with_turn(
        "历史截断测试",
        "user_a",
        "u1",
        "a1"
    )

    store.save_turn(conversation_id, "u2", "a2")
    store.save_turn(conversation_id, "u3", "a3")
    store.save_turn(conversation_id, "u4", "a4")

    messages = store.get_messages(conversation_id)
    assert len(messages) == 8

    model_calls = []
    def fake_call_model(question, history=None, *, pending_question=None):
        model_calls.append({
            "question": question,
            "history": history
        })

        return {
            "data": {
                "answer": "a5",
                "sources": []
            },
            "error": "",
            "record": {"状态码": 200},
            "pending_question": None,
            
        }

    def fake_get_model_caller():
        return fake_call_model

    monkeypatch.setitem(
        api.app.dependency_overrides,
        api.get_model_caller,
        fake_get_model_caller
    )

    response = client.post(
        "/chat",
        json={
            "question": "u5",
            "conversation_id": conversation_id
        }
    )

    assert response.status_code == 200
    assert model_calls == [{
        "question": "u5",
        "history": [
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "u3"},
            {"role": "assistant", "content": "a3"},
            {"role": "user", "content": "u4"},
            {"role": "assistant", "content": "a4"}
        ]
    }]
    messages_after = store.get_messages(conversation_id)

    assert len(messages_after) == 10
    assert messages_after[:2] == [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"}
    ]
    assert messages_after[-2:] == [
        {"role": "user", "content": "u5"},
        {"role": "assistant", "content": "a5"}
    ]

#没有令牌时返还401
def test_chat_missing_token():
    no_auth_client=TestClient(api.app)

    response=no_auth_client.post(
        "/chat",
        json={"question":"推荐杭州景点"}
    )

    assert response.status_code==401
    assert response.json()=={"detail":"缺失访问令牌"}


#user_b 不能继续 user_a 的会话。
def test_chat_forbidden_for_other_user(isolated_db):
    conversation_id=store.create_conversation_with_turn(
        "用户A的会话",
        "user_a",
        "推荐杭州景点",
        "可以参观西湖"
    )

    response=client.post(
        "/chat",
        json={
            "question":"继续推荐",
            "conversation_id":conversation_id
        },
        headers={
            "Authorization":"Bearer token_b"
        }
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "无权访问该对话"
    }

    messages=store.get_messages(conversation_id)
    assert len(messages)==2

def test_delete_own_conversation(isolated_db):
    conversation_id=store.create_conversation_with_turn(
        "待删除会话",
        "user_a",
        "用户消息",
        "助手回答"
    )

    response=client.delete(
        f"/conversations/{conversation_id}"
    )

    
    assert response.status_code == 200
    assert response.json() == {
        "status": "deleted",
        "conversation_id": conversation_id
    }

    assert store.get_conversation(conversation_id) is None
    assert store.get_messages(conversation_id) == []


def test_delete_other_user_conversation(isolated_db):
    conversation_id=store.create_conversation_with_turn(
        "用户A的会话",
        "user_a",
        "用户消息",
        "助手回答"
    )

    response=client.delete(
        f"/conversations/{conversation_id}",
        headers={
            "Authorization": "Bearer token_b"
        }
        )

    assert response.status_code==403
    assert response.json()=={
        "detail":"无权访问该对话"
    }
    assert store.get_conversation(conversation_id) is not None
    assert len(store.get_messages(conversation_id))==2


def test_get_own_conversation_detail(isolated_db):
    conversation_id=store.create_conversation_with_turn(
        "待查询会话",
        "user_a",
        "用户消息",
        "助手回答"
    )

    response=client.get(
        f"/conversations/{conversation_id}"
    )

    assert response.status_code==200

    data=response.json()

    assert data["conversation"]["id"]==conversation_id
    assert data["conversation"]["title"]=="待查询会话"
    assert data["conversation"]["owner_id"]=="user_a"
    assert len(data["messages"])==2
    assert data["messages"][0]["role"]=="user"
    assert data["messages"][1]["role"]=="assistant"
    assert data["messages"][0]["content"]=="用户消息"
    assert data["messages"][1]["content"]=="助手回答"


def test_get_other_user_conversation_detail(isolated_db):
    conversation_id=store.create_conversation_with_turn(
        "a消息",
        "user_a",
        "用户消息",
        "助手回答"
    )

    response=client.get(
        f"/conversations/{conversation_id}",
        headers={
            "Authorization": "Bearer token_b"
        }
    )

    assert response.status_code == 403
    assert response.json() == {
    "detail": "无权访问该对话"
}
    assert store.get_conversation(conversation_id) is not None
    assert len(store.get_messages(conversation_id)) == 2

def test_get_missing_conversation_detail(isolated_db):
    response=client.get(
        f"/conversations/999"
    )
    assert response.status_code == 404
    assert response.json() == {
    "detail": "会话不存在"
}

def test_get_invalid_conversation_id(isolated_db):
    response = client.get(
"/conversations/0"
)
    assert response.status_code == 422
    data = response.json()
    error = data["detail"][0]

    assert error["type"] == "greater_than_equal"
    assert error["loc"] == ["path", "conversation_id"]
    assert error["input"] == "0"


def test_get_conversation_without_auth():
    no_auth_client = TestClient(api.app)

    response = no_auth_client.get("/conversations/1")

    assert response.status_code == 401
    assert response.json() == {
        "detail": "缺失访问令牌"
    }

#测试判断需要澄清
def test_chat_clarification(monkeypatch):
    first = "晚上23:10下单，能保证30分钟内收到接车通知吗？"
    second = "艾客旅游千岛湖套餐1"
    clarification = "您预订的是哪个产品或套餐？"
    final_answer = "不能保证下单后30分钟内收到最终接车通知。"

    fake_rag = Mock(side_effect=[
        {
            "data": {"answer": clarification, "sources": []},
            "error": "",
            "record": None,
            "needs_clarification": True,
            "pending_question": first,
        },
        {
            "data": {"answer": final_answer, "sources": []},
            "error": "",
            "record": {"状态码": 200},
            "needs_clarification": False,
            "pending_question": None,
        },
    ])

    monkeypatch.setitem(
        api.app.dependency_overrides,
        api.get_model_caller,
        lambda:fake_rag,
    )

    first_response = client.post(
        "/chat",
        json={"question": first},
    )

    assert first_response.status_code == 200
    first_data = first_response.json()
    conversation_id = first_data["conversation_id"]

    assert first_data["needs_clarification"] is True
    assert first_data["data"]["answer"] == clarification
    assert store.get_pending_question(conversation_id) == first

    first_messages = store.get_messages(conversation_id)
    assert first_messages == [
        {"role": "user", "content": first},
        {"role": "assistant", "content": clarification},
    ]

    second_response = client.post(
        "/chat",
        json={
            "question": second,
            "conversation_id": conversation_id,
        },
    )

    assert second_response.status_code == 200
    second_data = second_response.json()

    # 检查两次调用收到的历史和状态
    assert fake_rag.call_count == 2
    assert fake_rag.call_args_list[0].args == (first,)
    assert fake_rag.call_args_list[0].kwargs == {
        "history": [],
            "pending_question": None}
    assert fake_rag.call_args_list[1].args == (second,)
    assert fake_rag.call_args_list[1].kwargs == {
        "history": first_messages,
        "pending_question": first,
    }

     # 完成后清除状态，但保留两轮聊天记录
    assert store.get_pending_question(conversation_id) is None
    assert store.get_messages(conversation_id) == first_messages + [
        {"role": "user", "content": second},
        {"role": "assistant", "content": final_answer},
    ]

    assert second_data["conversation_id"] == conversation_id
    assert second_data["needs_clarification"] is False
    assert second_data["data"]["answer"] == final_answer


#用户补充后仍缺信息
def test_chat_followup_still_needs_clarification(monkeypatch):
    first = "晚上23:10下单，能保证30分钟内收到接车通知吗？"
    second = "艾客旅游千岛湖套餐1"
    clarification = "您预订的是哪个产品或套餐？"
    second_clarification = "请再补充出行日期。"
    combined_question = first + "\n用户补充信息：" + second
    
    fake_rag = Mock(side_effect=[
        {
            "data": {"answer": clarification, "sources": []},
            "error": "",
            "record": None,
            "needs_clarification": True,
            "pending_question": first,
        },
        {
            "data": {"answer": second_clarification, "sources": []},
            "error": "",
            "record": {"状态码": 200},
            "needs_clarification": True,
            "pending_question": combined_question,
        },
    ])

    monkeypatch.setitem(
        api.app.dependency_overrides,
        api.get_model_caller,
        lambda:fake_rag,
    )
    first_response = client.post(
            "/chat",
            json={"question": first},
        )

    first_data = first_response.json()
    conversation_id = first_data["conversation_id"]
    first_messages=store.get_messages(conversation_id)

    second_response = client.post(
            "/chat",
            json={
                "question": second,
                "conversation_id": conversation_id,
            },
        )
    second_data = second_response.json()
    
    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_data["needs_clarification"] is True
    assert second_data["data"]["answer"] == second_clarification

    assert store.get_pending_question(conversation_id) == combined_question
    assert store.get_messages(conversation_id) == first_messages + [
        {"role": "user", "content": second},
        {"role": "assistant", "content": second_clarification},
]


#RAG 失败时，不覆盖旧消息和追问状态
def test_chat_error_preserves_pending_state(monkeypatch):
    pending_question = "原来等待补充的问题"
    supplement = "用户本次补充"

    conversation_id = store.create_conversation_with_turn(
        title="追问失败测试",
        owner_id="user_a",
        user_content=pending_question,
        assistant_content="请补充产品信息。",
        pending_question=pending_question,
    )
    original_messages = store.get_messages(conversation_id)

    fake_rag = Mock(return_value={
        "data": None,
        "error": "模拟 RAG 服务失败",
        "record": None,
        "pending_question": None,
    })

    monkeypatch.setitem(
        api.app.dependency_overrides,
        api.get_model_caller,
        lambda: fake_rag,
    )

    response = client.post(
        "/chat",
        json={
            "question": supplement,
            "conversation_id": conversation_id,
        },
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "模拟 RAG 服务失败"}

    fake_rag.assert_called_once_with(
        supplement,
        history=original_messages,
        pending_question=pending_question,
    )

    # 失败结果不能清除旧状态，也不能写入半轮聊天
    assert store.get_pending_question(conversation_id) == pending_question
    assert store.get_messages(conversation_id) == original_messages


#验证接入工具后是否回答正常
def test_chat_uses_tool_chat(monkeypatch):
    import app.tool_calling as tool_calling

    answer="你好，请告诉我目的地和天数"
    fake_model=Mock(return_value={
        "role":"assistant",
        "content":answer
    })

    monkeypatch.setattr(tool_calling,"call_tool_model",fake_model)
    monkeypatch.setitem(
        api.app.dependency_overrides,
        api.get_model_caller,
        lambda:api.call_tool_chat
    )

    assert api.get_model_caller() is api.call_tool_chat

    response=client.post("/chat",json={"question":"你好"})

    assert response.status_code==200
    data=response.json()

    assert data["data"]=={"answer":answer,"sources":[]}

    assert store.get_messages(data["conversation_id"])==[
        {"role":"user","content":"你好"},
        {"role":"assistant","content":answer}
    ]
    fake_model.assert_called_once()


#模型工具请求失败
def test_chat_tool_model_failure_does_not_save(monkeypatch):
    import app.tool_calling as tool_calling

    fake_model = Mock(
        side_effect=requests.exceptions.Timeout("模拟模型超时")
    )
    fake_create = Mock()

    monkeypatch.setattr(tool_calling, "call_tool_model", fake_model)
    monkeypatch.setattr(
        api, "create_conversation_with_turn", fake_create
    )
    monkeypatch.setitem(
        api.app.dependency_overrides,
        api.get_model_caller,
        lambda: api.call_tool_chat,
    )

    response = client.post("/chat", json={"question": "你好"})

    assert response.status_code == 502
    assert "模型请求失败" in response.json()["detail"]
    fake_model.assert_called_once()
    fake_create.assert_not_called()



#确认这些字段经过接口包装后没有丢失。
def test_chat_returns_tool_citations(monkeypatch):
    import app.tool_calling as tool_calling

    evidence = [{
        "chunk_id": "demo:chunk-1",
        "content": "示例线路每天上午9点集合。",
        "metadata": {
            "source_id": "S01",
            "source_title": "示例线路说明",
        },
    }]

    citations = [{
        "citation_id": "1",
        "chunk_id": "demo:chunk-1",
        "metadata": evidence[0]["metadata"],
    }]

    fake_run = Mock(return_value={
        "answer": "示例线路上午9点集合。",
        "sources": ["1"],
        "citations": citations,
        "evidence": evidence,
        "error": "",
    })
    monkeypatch.setattr(
        tool_calling, "run_tool_chat", fake_run
    )

    # 使用真实的接口包装函数
    monkeypatch.setitem(
        api.app.dependency_overrides,
        api.get_model_caller,
        lambda: api.call_tool_chat,
    )

    response = client.post(
        "/chat",
        json={"question": "示例线路几点集合？"},
    )

    assert response.status_code == 200
    result = response.json()

    assert result["data"] == {
        "answer": "示例线路上午9点集合。",
        "sources": ["1"],
    }
    assert result["citations"] == citations
    assert result["evidence"] == evidence
    assert result["error"] == ""

    fake_run.assert_called_once_with(
        "示例线路几点集合？",
        history=[],
    )


#核算成功
def test_quote_calculate_success(isolated_db):
    response=client.post(
        "/quotes/calculate",
        json={
            "adults":2,
            "children":0,
            "room_items":[],
            "meal_price":300,
            "transport_price":220,
            "guide_price":0,
            "ticket_price":120,
        }
    )

    assert response.status_code==200

    body=response.json()
    assert body["known_total"]=="1280.00"
    assert body["adult_known_total"]=="1280.00"
    assert body["person_costs"]["missing_items"]==["boat_price","entertainment_price"]
    assert "ok" not in body

#令牌无效
def test_calculate_quote_invalid_token():
    response=client.post(
        "/quotes/calculate",
        json={"adults": 2, "children": 0},
        headers={"Authorization":"Bearer bad"}
    )

    assert response.status_code==401

    body=response.json()
    assert body["detail"]=="访问令牌无效"

#人数为0
def test_calculate_quote_no_adult():
    response=client.post(
        "/quotes/calculate",
        json={
            "adults":0,
            "children":0,
        }
    )

    assert response.status_code==422

#页面 PUT 进去的内容，GET 能原样取回来。    
def test_draft_save_and_read():
    conversation_id = api.create_conversation_with_turn("杭州三日", "user_a", "问题", "回答")
    draft={"name":"杭州三日游","adults":2}

    put_response=client.put(f"/conversations/{conversation_id}/draft",
                            json={"draft":draft})

    assert put_response.status_code==200            

    get_response=client.get(f"/conversations/{conversation_id}/draft")
    assert get_response.status_code==200
    assert get_response.json()=={"draft":draft}


def test_read_draft_empty():
    conversation_id = api.create_conversation_with_turn("杭州三日", "user_a", "问题", "回答")
    get_response=client.get(f"/conversations/{conversation_id}/draft")
    assert get_response.status_code==200
    assert get_response.json()=={"draft":None}

def test_draft_forbidden_for_other_user():
    conversation_id = api.create_conversation_with_turn("杭州三日", "user_a", "问题", "回答")
    draft={"name":"杭州三日游","adults":2}
    get_response = client.get(f"/conversations/{conversation_id}/draft",
                      headers={"Authorization": "Bearer token_b"})
    
    put_response=client.put(f"/conversations/{conversation_id}/draft",
                                json={"draft":draft},
                                 headers={"Authorization": "Bearer token_b"})
    assert get_response.status_code==403
    assert put_response.status_code==403

def test_save_draft_rejects_extra_field():
    conversation_id = api.create_conversation_with_turn("杭州三日", "user_a", "问题", "回答")
    draft={"name":"杭州三日游","adults":2}
    response = client.put(
    f"/conversations/{conversation_id}/draft",
    json={"draft": draft, "owner_id": "user_b"},
)

    assert response.status_code==422
    get_response=client.get(
        f"/conversations/{conversation_id}/draft"
    )
    assert get_response.json()=={"draft":None}


#正常测试
def test_create_and_read_plan():
    draft={"name":"杭州三日游","adults":2}
    response=client.post(f"/plans",json={"draft":draft,"title":"杭州三日游"})
    plan_id=response.json()["plan_id"]    
    get_response=client.get(f"/plans/{plan_id}")

    assert response.status_code==200
    assert get_response.status_code==200
    assert get_response.json()["draft"]==draft
    assert get_response.json()["owner_id"]=="user_a"
    assert get_response.json()["current_version"]==1


#用户隔离：别人的方案看不到，别人的对话不能关联
def test_plan_access_control():
    b_headers={"Authorization":"Bearer token_b"}
    plan_id=client.post("/plans",json={"title":"杭州三日游","draft":{"adults":2}}).json()["plan_id"]
        #当前默认为a的
    # user_b 看不到、打不开 user_a 的方案
    assert client.get("/plans",headers=b_headers).json()=={"plans":[]}
    assert client.get(f"/plans/{plan_id}",headers=b_headers).status_code==403
    assert client.get("/plans/999").status_code==404

    # user_a 不能把方案关联到 user_b 的对话，也不会多建一个方案
    conversation_id=api.create_conversation_with_turn("杭州三日","user_b","问题","回答")
    #默认header为a
    response=client.post("/plans",json={"title":"杭州一日游","draft":{},"conversation_id":conversation_id})
    assert response.status_code==403
    assert len(client.get("/plans").json()["plans"])==1


#删除和复制：别人不能操作，自己复制后删除原方案，副本还在
def test_delete_and_copy_plan():
    b_headers={"Authorization":"Bearer token_b"}
    plan_id=client.post("/plans",json={"title":"杭州三日游","draft":{"adults":2}}).json()["plan_id"]

    assert client.post(f"/plans/{plan_id}/copy",headers=b_headers).status_code==403
    assert client.delete(f"/plans/{plan_id}",headers=b_headers).status_code==403

    copy_response=client.post(f"/plans/{plan_id}/copy")
    assert copy_response.status_code==200
    new_plan_id=copy_response.json()["plan_id"]
    assert client.get(f"/plans/{new_plan_id}").json()["title"]=="杭州三日游-副本"

    assert client.delete(f"/plans/{plan_id}").status_code==200
    assert client.get(f"/plans/{plan_id}").status_code==404
    assert client.get(f"/plans/{new_plan_id}").status_code==200

#冲突测试
def test_update_plan_version_conflict():
    plan_id=client.post("/plans",json={"title":"杭州三日游","draft":{"adults":2}}).json()["plan_id"]
    first_draft={"adults":3}
    second_draft={"adults":5}
    response=client.put(f"/plans/{plan_id}" ,json={"draft":first_draft,"base_version":1})
    a_response=client.put(f"/plans/{plan_id}", json={"draft":second_draft,"base_version":1})

    assert response.status_code==200
    assert a_response.status_code==409
    assert client.get(f"/plans/{plan_id}").json()["current_version"]==2
    assert client.get(f"/plans/{plan_id}").json()["draft"]==first_draft
    assert response.json()["version"]==2


def test_change_plan_status_errors():
    plan_id=client.post("/plans",json={"title":"杭州三日游","draft":empty_draft()}).json()["plan_id"]
    url=f"/plans/{plan_id}/status"
        # 跳过 pending，直接确认
    response=client.post(url,json={"status":"confirmed","base_version":1})
    assert response.status_code==409

    response=client.post(url,json={"status":"pending","base_version":2})
    assert response.status_code==409

    response=client.post(url,json={"status":"pending","base_version":1})
    assert response.status_code==200

    response=client.post(url,json={"status":"confirmed","base_version":1})
    assert response.status_code==422
    assert "成人单价" in response.json()["detail"]

    response=client.post(url,json={"status":"done","base_version":1})
    assert response.status_code==422


#保存时能修改方案标题
def test_update_plan_title():
    plan_id=client.post("/plans",json={"title":"杭州三日游","draft":{"adults":2}}).json()["plan_id"]

    response=client.put(f"/plans/{plan_id}",json={"draft":{"adults":3},"base_version":1,"title":"杭州四日游"})

    assert response.status_code==200
    assert client.get(f"/plans/{plan_id}").json()["title"]=="杭州四日游"


def test_request_body_too_large():
    response = client.post(
        "/plans",
        content=b"x" * (api.MAX_BODY_BYTES + 1),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert "X-Request-ID" in response.headers


def test_daily_quote_stops_at_limit():
    assert store.consume_daily_quota("user_a", "2026-10-31", 2) is True
    assert store.consume_daily_quota("user_a", "2026-10-31", 2) is True
    assert store.consume_daily_quota("user_a", "2026-10-31", 2) is False


def test_daily_quote_separates_user_and_day():
    assert store.consume_daily_quota("user_a", "2026-10-31", 1) is True
    assert store.consume_daily_quota("user_b", "2026-10-31", 1) is True
    assert store.consume_daily_quota("user_a", "2026-11-01", 1) is True


def test_chat_daily_limit(monkeypatch):
    model_calls=[]

    def fake_call_model(question,history=None,*,pending_question=None):
        model_calls.append(question)
        return{
            "data":{"answer":"推荐西湖","sources":[]},
            "error":"",
            "record":None,
            "pending_question":None,
        }

    monkeypatch.setitem(
        api.app.dependency_overrides,
        api.get_model_caller,
        lambda:fake_call_model,
    )
    monkeypatch.setattr(api,"DAILY_CHAT_LIMIT",1)

    first=client.post("/chat",json={"question":"推荐杭州景点"})
    second=client.post("/chat",json={"question":"推荐杭州美食"})

    assert first.status_code==200
    assert second.status_code==429
    assert len(model_calls)==1


#读历史会话
def test_list_conversations_newest_first():
    first = store.create_conversation("第一个会话", "user_a")
    second = store.create_conversation("第二个会话", "user_a")
    store.save_turn(first, "问题", "回答")

    conn = store.get_connection()
    conn.execute(
        "UPDATE messages SET created_at='2030-01-01 00:00:00' WHERE conversation_id=?",
        (first,),
    )
    conn.commit()
    conn.close()

    result = store.list_conversations("user_a")

    assert [item["id"] for item in result] == [first, second]


#测试历史会话隔离
def test_conversation_list_only_shows_own():
    first=store.create_conversation("会话a","user_a")
    second=store.create_conversation("会话b","user_b")
    
    response=client.get("/conversations")

    assert response.status_code==200
    ids = [item["id"] for item in response.json()["conversations"]]
    assert ids == [first]


#模拟整理草稿
def test_generate_draft_uses_all_messages(monkeypatch):
    conversation_id = store.create_conversation("杭州", "user_a")
    for index in range(5):
        store.save_turn(conversation_id, f"问题{index}", f"回答{index}")

    seen = {}

    def fake_generate(messages, target_id):
        seen["count"] = len(messages)
        return {"draft": {"name": "杭州两日游"}, "error": ""}

    monkeypatch.setattr(api, "generate_draft", fake_generate)

    response = client.post(f"/conversations/{conversation_id}/draft/generate")

    assert response.status_code == 200
    assert response.json()["draft"]["name"] == "杭州两日游"
    assert seen["count"] == 10

#模拟空聊天报错
def test_generate_draft_empty_conversation(monkeypatch):
    conversation_id = store.create_conversation("杭州", "user_a")
    fake_generate = Mock()
    monkeypatch.setattr(api, "generate_draft", fake_generate)

    response = client.post(f"/conversations/{conversation_id}/draft/generate")

    assert response.status_code == 422
    fake_generate.assert_not_called()

#模拟其他用户是否隔离
def test_generate_draft_forbidden_for_other_user(monkeypatch):
    conversation_id=store.create_conversation("杭州","user_b")
    fake_generate=Mock()
    monkeypatch.setattr(api,"generate_draft",fake_generate)

    response=client.post(f"/conversations/{conversation_id}/draft/generate")

    assert response.status_code==403
    fake_generate.assert_not_called()


#保存过草案的会话，/chat 会把草案内容传给模型。
def test_chat_passage_draft_to_model(monkeypatch):
    conversation_id=store.create_conversation("杭州","user_a")
    draft = to_draft(ExtractedDraft(adult_prices={"meal_price": 80}), conversation_id)
    store.save_draft(conversation_id,draft)
    seen=[]

    def fake_call_model(question,history=None,*,pending_question=None):
        seen.append(history)
        return {
            "data": {"answer": "好的", "sources": []},
            "error": "",
            "record": None,
            "pending_question": None,
        }


    monkeypatch.setitem(
        api.app.dependency_overrides,
        api.get_model_caller,
        lambda: fake_call_model,
    )


    response=client.post(
        "/chat",
        json={"question": "餐费多少", "conversation_id": conversation_id},
    )

    assert response.status_code==200
    assert seen[0][0]["role"]=="system"
    assert "餐饮80.0元" in seen[0][0]["content"]


def fake_draft_chat(question, history=None, *, pending_question=None):
    return {
        "data": {"answer": "好的", "sources": []},
        "error": "",
        "record": None,
        "pending_question": None,
        "draft_requested": True,
    }


def test_chat_generates_draft_with_current_turn(monkeypatch):
    seen = []

    def fake_generate(messages, conversation_id):
        seen.extend(messages)
        return {"draft": {"name": "杭州"}, "error": ""}

    monkeypatch.setitem(api.app.dependency_overrides, api.get_model_caller, lambda: fake_draft_chat)
    monkeypatch.setattr(api, "generate_draft", fake_generate)

    response = client.post("/chat", json={"question": "餐费80，整理成草案"})

    assert response.status_code == 200
    assert response.json()["generated_draft"] == {"name": "杭州"}
    assert seen[0]["content"] == "餐费80，整理成草案"


def test_chat_keeps_answer_when_draft_fails(monkeypatch):
    monkeypatch.setitem(api.app.dependency_overrides, api.get_model_caller, lambda: fake_draft_chat)
    monkeypatch.setattr(
        api, "generate_draft",
        lambda messages, conversation_id: {"draft": None, "error": "草案整理失败，请重试"},
    )

    response = client.post("/chat", json={"question": "整理成草案"})

    assert response.status_code == 200
    assert response.json()["data"]["answer"] == "好的"
    assert response.json()["generated_draft"] is None
    assert response.json()["draft_error"] == "草案整理失败，请重试"


def test_chat_keeps_answer_when_quota_runs_out(monkeypatch):
    fake_generate = Mock()
    monkeypatch.setitem(api.app.dependency_overrides, api.get_model_caller, lambda: fake_draft_chat)
    monkeypatch.setattr(api, "generate_draft", fake_generate)
    monkeypatch.setattr(api, "DAILY_CHAT_LIMIT", 1)

    response = client.post("/chat", json={"question": "整理成草案"})

    assert response.status_code == 200
    assert response.json()["draft_error"] == "今日调用次数已用完"
    fake_generate.assert_not_called()


#模拟工具
def knowledge_call():
    return {
        "id": "call_search",
        "type": "function",
        "function": {"name": "knowledge_search", "arguments": '{"query": "这个团多少钱"}'},
    }

#如果进行了澄清
def test_clarification_returns_without_second_model_call(monkeypatch):
    fake_model = Mock(return_value={
        "role": "assistant", "content": None, "tool_calls": [knowledge_call()],
    })
    monkeypatch.setattr("app.tool_calling.call_tool_model", fake_model)
    monkeypatch.setattr(
        "app.tool_calling.execute_tool",
        Mock(return_value={
            "ok": True, "data": {"clarification": "是哪家商家？"}, "error": None,
        }),
    )

    result = run_tool_chat("这个团多少钱")

    assert result == {"answer": "是哪家商家？", "error": ""}
    assert fake_model.call_count == 1


#测试建立的小本本
def test_tool_chat_builds_search_state(monkeypatch):
    seen = {}

    def fake_execute(tool_name, raw):
        seen.update(search_state_var.get())
        return {"ok": True, "data": {"evidence": []}, "error": None}

    fake_model = Mock(side_effect=[
        {"role": "assistant", "content": None, "tool_calls": [knowledge_call()]},
        {"role": "assistant", "content": "没有查到"},
    ])
    monkeypatch.setattr("app.tool_calling.call_tool_model", fake_model)
    monkeypatch.setattr("app.tool_calling.execute_tool", fake_execute)
    history = [
        {"role": "system", "content": "草案内容"},
        {"role": "user", "content": "杭州两日游"},
    ]

    run_tool_chat("这个团多少钱", history=history)

    assert seen["history"] == [  #查过滤，并带上本轮原话
        {"role": "user", "content": "杭州两日游"},
        {"role": "user", "content": "这个团多少钱"},
    ]
    assert search_state_var.get() is None  #查小本子在不在