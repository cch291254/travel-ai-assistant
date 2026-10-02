from unittest import mock
from examples.week5_day3_my_client import call_model
from unittest.mock import Mock, patch
import requests

def make_200_response(answer="模拟回答",finish_reason="stop"):
    
    fake_response=Mock()
    fake_response.status_code=200
    fake_response.json.return_value={"choices":[
    {
        "message":{"content":answer},
                "finish_reason":finish_reason,
            },],
                                    
    "usage":{
            "prompt_tokens":10,
            "completion_tokens":5,
            "total_tokens":15,
    }}
    return fake_response



def test_empty_question():
    result = call_model("   ")

    assert result["answer"] == ""
    assert result["record"] is None
    assert result["error"] == "问题不能为空"
def test_question_too_long():
    result=call_model("问"*1001)


    assert result["answer"]==""
    assert result["record"] is None
    assert result["error"]=="问题过长"
def test_success_response(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY","test-key")
    fake_response=make_200_response(answer="模拟回答",finish_reason="stop")
    with patch(
        "examples.week5_day3_my_client.requests.post",
        return_value=fake_response,
    ) as mock_post:
        result=call_model("测试问题")


        assert result["answer"]=="模拟回答"
        assert result["error"]==""
        assert result["record"]["状态码"]==200
        assert result["record"]["结束原因"]=="stop"
        assert result["record"]["总tokens"] == 15
        assert mock_post.call_count == 1
def test_length_response(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY","test-key")
    fake_response=make_200_response(answer="模拟回答",finish_reason="length")
    with patch(
        "examples.week5_day3_my_client.requests.post",
        return_value=fake_response,
    ) as mock_post:
        result=call_model("测试问题")


        assert result["answer"]=="模拟回答"
        assert result["error"]=="回答不完整"
        assert result["record"]["状态码"]==200
        assert result["record"]["结束原因"]=="length"
        assert result["record"]["总tokens"] == 15
        assert mock_post.call_count == 1
def test_empty_answer_response(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY","test-key")
    fake_response=make_200_response(answer="",finish_reason="stop")
    with patch(
        "examples.week5_day3_my_client.requests.post",
        return_value=fake_response,
    ) as mock_post:
        result=call_model("测试问题")


        assert result["answer"]==""
        assert result["error"]=="模型未返回完整回答"
        assert result["record"]["状态码"]==200
        assert result["record"]["结束原因"]=="stop"
        assert result["record"]["总tokens"] == 15
        assert mock_post.call_count == 1

def test_http_401_does_not_retry(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    fake_response = Mock()
    fake_response.status_code = 401
    fake_response.text = "unauthorized"

    with patch(
        "examples.week5_day3_my_client.requests.post",
        return_value=fake_response,
    ) as mock_post:
        result = call_model("测试问题")

    assert result["answer"] == ""
    assert result["record"]["状态码"]==401
    assert result["error"] == "HTTP请求失败,状态码401,不允许重试"
    assert mock_post.call_count == 1
    assert result["record"]["重试次数"] == 0
def test_question_must_be_string():
    result = call_model(None)

    assert result["answer"] == ""
    assert result["record"] is None
    assert result["error"] == "问题必须是字符串"
def test_503_then_success(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    response_503 = Mock()
    response_503.status_code = 503

    response_200 = make_200_response(answer="重试成功",finish_reason="stop")
    with patch(
        "examples.week5_day3_my_client.time.sleep"
    ) as mock_sleep:
        with patch(
            "examples.week5_day3_my_client.requests.post",
            side_effect=[response_503, response_200],
        ) as mock_post:
            result = call_model("测试重试")
    
    assert result["answer"] == "重试成功"
    assert result["error"] == ""
    assert result["record"]["状态码"] == 200
    assert result["record"]["重试次数"] == 1
    assert mock_post.call_count == 2
    assert mock_sleep.call_count == 1
def test_503_retry_exhausted(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    response_503 = Mock()
    response_503.status_code = 503
    response_503.text = "service unavailable"
    with patch(
        "examples.week5_day3_my_client.time.sleep"
    ) as mock_sleep:
        with patch(
            "examples.week5_day3_my_client.requests.post",
            side_effect=[response_503, response_503, response_503],
        ) as mock_post:
            result = call_model("测试重试耗尽")
    assert result["answer"] == ""
    assert result["record"]["状态码"] == 503
    assert result["record"]["重试次数"] == 2
    assert mock_post.call_count == 3
    assert mock_sleep.call_count == 2
    response_503.json.assert_not_called()
def test_timeout_then_success(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    response_200 = make_200_response(answer="超时后重试成功",finish_reason="stop")
    with patch(
        "examples.week5_day3_my_client.time.sleep"
    ) as mock_sleep:
        with patch(
            "examples.week5_day3_my_client.requests.post",
            side_effect=[
                requests.exceptions.Timeout("连接超时"),
                response_200,
            ],
        ) as mock_post:
            result = call_model("测试网络超时")
    assert result["answer"]=="超时后重试成功"
    assert result["error"]==""
    assert result["record"]["状态码"]==200
    assert result["record"]["重试次数"]==1
    assert mock_post.call_count==2
    assert mock_sleep.call_count==1

def test_timeout_retry_exhausted(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    with patch(
        "examples.week5_day3_my_client.time.sleep"
    ) as mock_sleep:
        with patch(
            "examples.week5_day3_my_client.requests.post",
            side_effect=requests.exceptions.Timeout("连接超时"),
        ) as mock_post:
            result = call_model("测试连续超时")
    assert result["answer"] == ""
    assert result["record"]["状态码"] is None
    assert result["record"]["重试次数"] == 2
    assert mock_post.call_count == 3
    assert mock_sleep.call_count == 2
