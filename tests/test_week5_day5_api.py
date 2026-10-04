from fastapi.testclient import TestClient
import app.week5_day5_api as api


client=TestClient(api.app)

def test_heakth():
    response=client.get("/health")

    assert response.status_code==200
    assert response.json()=={"status":"ok"}

def test_not_exist():
    response=client.get("/not_exist")

    assert response.status_code==404
    assert response.json()=={"detail":"Not Found"}

def test_chat_success(monkeypatch):
    def fake_call_model(question):
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
        json={"question":"推荐杭州景点"},
    )
    result=response.json()

    assert result["data"]["answer"]=="推荐西湖"
    assert result["data"]["sources"]==[]
    assert result["error"]==""
    assert result["record"]["状态码"]==200
    assert response.status_code == 200

def test_chat_empty_question(monkeypatch):
    calls = []
    def fake_call_model(question):
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
    def fake_call_model(question):
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
