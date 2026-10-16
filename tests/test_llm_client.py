from app.llm_client import call_model
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
        "app.llm_client.requests.post",
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
        "app.llm_client.requests.post",
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
        "app.llm_client.requests.post",
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
        "app.llm_client.requests.post",
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
        "app.llm_client.time.sleep"
    ) as mock_sleep:
        with patch(
            "app.llm_client.requests.post",
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
        "app.llm_client.time.sleep"
    ) as mock_sleep:
        with patch(
            "app.llm_client.requests.post",
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
        "app.llm_client.time.sleep"
    ) as mock_sleep:
        with patch(
            "app.llm_client.requests.post",
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
        "app.llm_client.time.sleep"
    ) as mock_sleep:
        with patch(
            "app.llm_client.requests.post",
            side_effect=requests.exceptions.Timeout("连接超时"),
        ) as mock_post:
            result = call_model("测试连续超时")
    assert result["answer"] == ""
    assert result["record"]["状态码"] is None
    assert result["record"]["重试次数"] == 2
    assert mock_post.call_count == 3
    assert mock_sleep.call_count == 2

#测试资料获取是否正常
def test_context_is_sent(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    fake_response = make_200_response()
    context = "[1] 午餐费用自理。"

    with patch(
        "app.llm_client.requests.post",
        return_value=fake_response,
    ) as mock_post:
        result = call_model("午餐包含吗？", context=context)

    messages = mock_post.call_args.kwargs["json"]["messages"]

    assert result["error"] == ""
    assert messages[-1]["role"] == "user"
    assert context in messages[-1]["content"]
    assert "午餐包含吗？" in messages[-1]["content"]
    assert context not in messages[0]["content"]


def test_output_budget_can_be_set_without_changing_default(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    with patch("app.llm_client.requests.post", return_value=make_200_response()) as mock_post:
        call_model("整理检索问题", max_tokens=1024)
        assert mock_post.call_args.kwargs["json"]["max_tokens"] == 1024
        call_model("回答问题")
        assert mock_post.call_args.kwargs["json"]["max_tokens"] == 300


def test_invalid_output_budget_does_not_send_request():
    with patch("app.llm_client.requests.post") as mock_post:
        for budget in (0, -1, True, "300", None):
            result = call_model("测试问题", max_tokens=budget)
            assert result["error"] == "max_tokens必须是正整数"
    mock_post.assert_not_called()
