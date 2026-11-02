"""全部使用模拟响应，不调用真实模型，也不读取真实API Key。"""

import importlib.util
from pathlib import Path
from unittest.mock import Mock, call

import pytest
import requests


client_path = Path(__file__).resolve().parents[1] / "examples" / "week5_day3_deepseek_client.py"
spec = importlib.util.spec_from_file_location("day3_client_under_test", client_path)
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


def fake_response(status_code=200, finish_reason="stop", answer="推荐西湖"):
    response = Mock()
    response.status_code = status_code
    response.text = ""
    response.json.return_value = {
        "model": "test-model",
        "choices": [{"message": {"content": answer}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 52, "completion_tokens": 59, "total_tokens": 111},
    }
    return response


@pytest.fixture
def mocked_client(monkeypatch):
    monkeypatch.setattr(client, "load_dotenv", lambda: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/")
    monkeypatch.setenv("DEEPSEEK_MODEL", "test-model")
    post = Mock(return_value=fake_response())
    sleep = Mock()
    monkeypatch.setattr(client.requests, "post", post)
    monkeypatch.setattr(client.time, "sleep", sleep)
    return post, sleep


@pytest.mark.parametrize("question", ["", "   ", "问" * 1001, None])
def test_invalid_input_does_not_send_request(mocked_client, question):
    post, sleep = mocked_client
    result = client.call_model(question)
    assert result["success"] is False
    assert result["records"] == []
    assert result["error"]
    post.assert_not_called()
    sleep.assert_not_called()


def test_success_cleans_input_and_records_usage(mocked_client):
    post, sleep = mocked_client
    result = client.call_model("  推荐杭州三日游  ")
    assert result["success"] is True
    assert result["answer"] == "推荐西湖"
    record = result["records"][0]
    assert record["状态码"] == 200
    assert record["总tokens"] == 111
    assert record["重试次数"] == 0
    assert record["结果"] == "正常结束"
    assert record["耗时秒"] >= 0
    payload = post.call_args.kwargs["json"]
    assert payload["messages"][1]["content"] == "推荐杭州三日游"
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["max_tokens"] == 300
    assert post.call_args.args[0] == "https://api.deepseek.com/chat/completions"
    assert "test-only-key" not in str(result)
    sleep.assert_not_called()


def test_exact_input_length_is_accepted(mocked_client):
    post, _ = mocked_client
    assert client.call_model("问" * 20, max_input_chars=20)["success"] is True
    assert post.call_count == 1


def test_missing_key_does_not_send_request(mocked_client, monkeypatch):
    post, _ = mocked_client
    monkeypatch.delenv("DEEPSEEK_API_KEY")
    result = client.call_model("推荐杭州三日游")
    assert result["records"] == []
    assert "API Key" in result["error"]
    post.assert_not_called()


@pytest.mark.parametrize("status_code", [400, 401, 402, 403, 404, 422])
def test_permanent_http_error_is_not_retried(mocked_client, status_code):
    post, sleep = mocked_client
    response = fake_response(status_code)
    post.return_value = response
    result = client.call_model("推荐杭州三日游")
    assert result["success"] is False
    assert post.call_count == 1
    assert result["records"][0]["状态码"] == status_code
    assert result["records"][0]["总tokens"] is None
    response.json.assert_not_called()
    sleep.assert_not_called()


@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
def test_temporary_http_error_is_retried(mocked_client, status_code):
    post, sleep = mocked_client
    post.side_effect = [fake_response(status_code), fake_response()]
    result = client.call_model("推荐杭州三日游")
    assert result["success"] is True
    assert post.call_count == 2
    assert [r["重试次数"] for r in result["records"]] == [0, 1]
    assert result["records"][0]["结果"] == "HTTP失败"
    sleep.assert_called_once_with(1)


def test_three_failures_stop_without_final_sleep(mocked_client):
    post, sleep = mocked_client
    post.return_value = fake_response(503)
    result = client.call_model("推荐杭州三日游")
    assert post.call_count == 3
    assert len(result["records"]) == 3
    assert "次数耗尽" in result["error"]
    assert sleep.call_args_list == [call(1), call(1)]


def test_http_failure_keeps_final_error_body_out_of_records(mocked_client):
    post, _ = mocked_client
    post.return_value = fake_response(401)
    post.return_value.text = "Authentication Fails"
    result = client.call_model("推荐杭州三日游")
    assert "Authentication Fails" in result["error"]
    assert "Authentication Fails" not in str(result["records"])


@pytest.mark.parametrize("error", [requests.exceptions.Timeout(), requests.exceptions.ConnectionError()])
def test_network_error_then_success(mocked_client, error):
    post, sleep = mocked_client
    post.side_effect = [error, fake_response()]
    result = client.call_model("推荐杭州三日游")
    assert result["success"] is True
    assert result["records"][0]["状态码"] is None
    assert result["records"][0]["总tokens"] is None
    assert result["records"][0]["结果"] == "网络异常"
    sleep.assert_called_once_with(1)


def test_network_errors_stop_at_attempt_limit(mocked_client):
    post, sleep = mocked_client
    post.side_effect = requests.exceptions.Timeout()
    result = client.call_model("推荐杭州三日游")
    assert result["success"] is False
    assert post.call_count == 3
    assert len(result["records"]) == 3
    assert sleep.call_count == 2


@pytest.mark.parametrize("error", [requests.exceptions.SSLError(), requests.exceptions.InvalidURL()])
def test_connection_configuration_error_is_not_retried(mocked_client, error):
    post, sleep = mocked_client
    post.side_effect = error
    result = client.call_model("推荐杭州三日游")
    assert result["success"] is False
    assert post.call_count == 1
    sleep.assert_not_called()


def test_non_json_response_is_not_retried(mocked_client):
    post, sleep = mocked_client
    post.return_value.json.side_effect = requests.exceptions.JSONDecodeError("invalid", "", 0)
    result = client.call_model("推荐杭州三日游")
    assert result["success"] is False
    assert result["records"][0]["结果"] == "响应解析失败"
    assert post.call_count == 1
    sleep.assert_not_called()


def test_missing_response_fields_are_not_retried(mocked_client):
    post, sleep = mocked_client
    post.return_value.json.return_value = {"choices": []}
    result = client.call_model("推荐杭州三日游")
    assert result["success"] is False
    assert result["records"][0]["结果"] == "响应解析失败"
    assert post.call_count == 1
    sleep.assert_not_called()


def test_truncated_answer_is_preserved_but_not_retried(mocked_client):
    post, sleep = mocked_client
    post.return_value = fake_response(finish_reason="length", answer="上午：西湖；下午：")
    result = client.call_model("推荐杭州三日游")
    assert result["success"] is False
    assert result["answer"] == "上午：西湖；下午："
    assert result["records"][0]["总tokens"] == 111
    assert result["records"][0]["结果"] == "回答截断"
    assert post.call_count == 1
    sleep.assert_not_called()


@pytest.mark.parametrize("answer", ["", "   ", None])
def test_empty_answer_is_not_success_or_retried(mocked_client, answer):
    post, sleep = mocked_client
    post.return_value = fake_response(answer=answer)
    result = client.call_model("推荐杭州三日游")
    assert result["success"] is False
    assert post.call_count == 1
    sleep.assert_not_called()


def test_zero_attempts_do_not_send_request(mocked_client):
    post, _ = mocked_client
    result = client.call_model("推荐杭州三日游", max_attempts=0)
    assert result["success"] is False
    assert result["records"] == []
    post.assert_not_called()
