from fastapi.testclient import TestClient
import app.week5_day5_api as api
import examples.week5_day4_structured_output as structured_output
import pytest
import app.conversation_store as store


client=TestClient(api.app)

@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    test_db_path = tmp_path / "test_conversation.db"

    monkeypatch.setattr(
        store,
        "DB_PATH",
        test_db_path
    )

    store.init_db()



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
    def fake_call_model(question,history=None):
        model_calls.append({
            "question":question,
            "history":history
        })
        return{
            "data":{
                "answer":"推荐西湖",
                "sources":[],
            },
            "error":"",
            "record":{"状态码":200},
        }
    def fake_create_conversation_with_turn(
        title,
        owner_id,
        user_content,
        assistant_content
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
    def fake_call_model(question,history=None):
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
        json={"question":""},
    )
    result=response.json()

    assert response.status_code == 422
    assert calls==[]

def test_chat_whitespace_question(monkeypatch):
    calls = []
    def fake_call_model(question,history=None):
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
    def fake_call_model(question,history=None):
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
    def fake_call_model(question,history=None):
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

def test_chat_missing_sources(monkeypatch):
    def fake_call_model(question,system_prompt,json_mode=False,history=None):
        return {
            "answer": '{"answer": "推荐西湖"}',
            "error": "",
            "record": {"状态码": 200},
        }
    monkeypatch.setattr(
        structured_output,
        "call_model",
        fake_call_model,
    )

    response = client.post(
        "/chat",
        json={"question": "推荐杭州景点"},
    )
    result = response.json()

    assert response.status_code == 502
    assert "sources" in result["detail"]


def test_chat_existing_conversation(monkeypatch, isolated_db):
    conversation_id = store.create_conversation_with_turn(
    "杭州旅行",
    "user_a",
    "我想去杭州玩两天",
    "可以安排西湖和灵隐寺"
    )
    model_calls = []

    def fake_call_model(question, history=None):
        model_calls.append({
            "question": question,
            "history": history
        })

        return {
            "data": {
                "answer": "下雨时可以安排博物馆",
                "sources": []
            },
            "error": "",
            "record": {"状态码": 200}
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

    def fake_call_model(question, history=None):
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
            "record": {"状态码": 200}
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
    def fake_call_model(question, history=None):
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
            "record": {"状态码": 200}
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