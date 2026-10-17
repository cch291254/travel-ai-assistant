from unittest.mock import patch,Mock

import pytest
from fastapi.testclient import TestClient

import app.conversation_store as store


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
        "detail":"无权删除该对话"
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
    "detail": "无权访问该会话"
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