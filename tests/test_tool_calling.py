import json

from app.tool_calling import execute_model_tool_call
from unittest.mock import Mock
from app.tool_calling import execute_model_tool_call, call_tool_model,run_tool_chat
from app.tools import build_model_tools
import requests
import pytest



def test_execute_model_tool_call_queto():
    tool_call={
        "id":"call_demo_1",
        "type":"function",
        "function":{
            "name":"calculate_quote",
            "arguments":'{"adults":2,"children":0,"meal_price":"50.00"}'
        }
    }

    message=execute_model_tool_call(tool_call)

    assert message["role"]=="tool"
    assert message["tool_call_id"]=="call_demo_1"
    result=json.loads(message["content"])
    assert result["ok"] is True
    assert result["data"]["person_costs"]["adult_base"]=="50.00"

#测试错误
def test_execute_model_tool_call_invalid_json():
    tool_call={
        "id":"call_demo_1",
        "type":"function",
        "function":{
            "name":"calculate_quote",
            "arguments":'{"adults":2,',
        }
    }

    message=execute_model_tool_call(tool_call)

    assert message["role"]=="tool"
    assert message["tool_call_id"]=="call_demo_1"
    result=json.loads(message["content"])
    assert result["ok"] is False
    assert result["error"]["code"]=="INVALID_ARGUMENT"


#测试请求工具选择
def test_call_tool_model_returns_tool_calls(monkeypatch):
    monkeypatch.setattr("app.tool_calling.load_dotenv", Mock())
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")

    messages = [
        {"role": "user", "content": "两位成人，每人餐费50元，帮我计算"}
    ]

    tool_call={
            "id":"call_demo_1",
            "type":"function",
            "function":{
                "name":"calculate_quote",
                "arguments":'{"adults":2,"children":0,"meal_price":"50.00"}'
            }
        }

    expected_message = {
    "role": "assistant",
    "content": None,
    "tool_calls": [tool_call],
}

    fake_response=Mock()
    fake_response.json.return_value = {
    "choices": [
        {"message": expected_message}
    ]
}

    fake_post=Mock(return_value=fake_response)
    monkeypatch.setattr("app.tool_calling.requests.post", fake_post)

    result=call_tool_model(messages)

    assert result==expected_message
    fake_post.assert_called_once()

    payload=fake_post.call_args.kwargs["json"]
    assert payload["messages"]==messages
    assert payload["tools"]==build_model_tools()
    assert "response_format" not in payload


def test_call_tool_model_enables_json_output(monkeypatch):
    monkeypatch.setattr("app.tool_calling.load_dotenv", Mock())
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")
    messages = [{"role": "system", "content": "只返回包含answer和sources的JSON对象。"}]
    expected_message = {
        "role": "assistant",
        "content": '{"answer":"示例回答[1]。","sources":["1"]}',
    }
    fake_response = Mock()
    fake_response.json.return_value = {
        "choices": [{"finish_reason": "stop", "message": expected_message}],
    }
    fake_post = Mock(return_value=fake_response)
    monkeypatch.setattr("app.tool_calling.requests.post", fake_post)

    result = call_tool_model(messages, json_mode=True)

    assert result == expected_message
    payload = fake_post.call_args.kwargs["json"]
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"] == messages
    assert payload["tools"] == build_model_tools()
    fake_post.assert_called_once()



#不使用工具
def test_run_tool_chat_direct_answer(monkeypatch):
    fake_model = Mock(return_value={
        "role": "assistant",
        "content": "你好，请告诉我目的地和天数。",
    })
    fake_execute = Mock()

    monkeypatch.setattr("app.tool_calling.call_tool_model", fake_model)
    monkeypatch.setattr("app.tool_calling.execute_model_tool_call", fake_execute)

    result = run_tool_chat("你好")

    assert result == {
        "answer": "你好，请告诉我目的地和天数。",
        "error": "",
    }
    fake_model.assert_called_once()
    fake_execute.assert_not_called()


#执行一次工具
def test_run_tool_chat_executes_quote(monkeypatch):
    tool_call = {
        "id": "call_demo_1",
        "type": "function",
        "function": {
            "name": "calculate_quote",
            "arguments": '{"adults":2,"children":0,"meal_price":"50.00"}',
        },
    }

    tool_request = {
        "role": "assistant",
        "content": None,
        "tool_calls": [tool_call],
    }
    final_reply = {
        "role": "assistant",
        "content": "成人每人已知费用小计50元，需员工确认。",
    }

    fake_model = Mock(side_effect=[tool_request, final_reply])
    monkeypatch.setattr("app.tool_calling.call_tool_model", fake_model)

    result = run_tool_chat("2位成人、0位儿童，每人餐费50元，帮我计算")

    assert result == {"answer": final_reply["content"], "error": ""}
    assert fake_model.call_count == 2

    # 取出最后一次请求模型时传入的 messages
    messages = fake_model.call_args.args[0]

    assert messages[-2] == tool_request

    tool_message = messages[-1]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call_demo_1"

    tool_result = json.loads(tool_message["content"])
    assert tool_result["ok"] is True
    assert tool_result["data"]["person_costs"]["adult_base"] == "50.00"



#多轮退出
def test_run_tool_chat_stops_at_round_limit(monkeypatch):
    tool_call = {
        "id": "call_loop_1",
        "type": "function",
        "function": {
            "name": "calculate_quote",
            "arguments": '{"adults":2,"children":0,"meal_price":"50.00"}',
        },
    }

    fake_model = Mock(return_value={
        "role": "assistant",
        "content": None,
        "tool_calls": [tool_call],
    })
    monkeypatch.setattr("app.tool_calling.call_tool_model", fake_model)

    result = run_tool_chat("帮我计算费用", max_rounds=2)

    assert fake_model.call_count == 2
    assert result["answer"] == ""
    assert "轮数上限" in result["error"]


#在最终调用验证是否会超时
def test_run_tool_chat_handles_model_timeout(monkeypatch):
    fake_model = Mock(
        side_effect=requests.exceptions.Timeout("测试超时")
    )
    fake_execute = Mock()

    monkeypatch.setattr("app.tool_calling.call_tool_model", fake_model)
    monkeypatch.setattr("app.tool_calling.execute_model_tool_call", fake_execute)

    result = run_tool_chat("帮我计算费用")

    assert result["answer"] == ""
    assert "模型请求失败" in result["error"]
    fake_model.assert_called_once()
    fake_execute.assert_not_called()


def test_run_tool_chat_returns_knowledge_citations(monkeypatch):
    # 模拟知识库检索到的一条资料
    evidence = [
        {
            "chunk_id": "demo:chunk-1",
            "content": "示例线路每天上午9点集合。",
            "metadata": {
                "source_id": "S01",
                "source_title": "示例线路说明",
            },
        },
        {
            "chunk_id": "demo:chunk-2",
            "content": "示例酒店提供早餐。",
            "metadata": {
                "source_id": "S02",
                "source_title": "示例酒店说明",
            },
        },
    ]

    fake_execute = Mock(return_value={
        "ok": True,
        "data": {"evidence": evidence},
        "error": None,
    })
    monkeypatch.setattr(
        "app.tool_calling.execute_tool", fake_execute
    )

    # 模型第一次要求检索，第二次根据资料回答
    tool_call = {
        "id": "call_knowledge_1",
        "type": "function",
        "function": {
            "name": "knowledge_search",
            "arguments": '{"query": "示例线路几点集合？"}',
        },
    }

    fake_model = Mock(side_effect=[
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [tool_call],
        },
        {
            "role": "assistant",
            "content": json.dumps({
                "answer": "示例线路上午9点集合[1]。",
                "sources": ["1", "2"],
            }, ensure_ascii=False),
        },
    ])
    monkeypatch.setattr(
        "app.tool_calling.call_tool_model", fake_model
    )

    result = run_tool_chat("示例线路几点集合？")

    assert result["error"] == ""
    assert result["answer"] == "示例线路上午9点集合[1]。"
    assert result["sources"] == ["1"]
    assert result["evidence"] == evidence
    assert result["citations"] == [{
        "citation_id": "1",
        "chunk_id": "demo:chunk-1",
        "metadata": evidence[0]["metadata"],
    }]
    assert fake_model.call_args_list[0].kwargs == {"json_mode": False}
    assert fake_model.call_args_list[1].kwargs == {"json_mode": True}

    fake_execute.assert_called_once_with(
        "knowledge_search",
        {"query": "示例线路几点集合？"},
    )
    assert fake_model.call_count == 2

    # 检查第二次请求模型时，工具消息中已有编号和正文
    messages = fake_model.call_args.args[0]
    tool_message = messages[-1]
    tool_result = json.loads(tool_message["content"])

    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == "call_knowledge_1"
    context = tool_result["data"]["context"]
    assert "[1]" in context
    assert "示例线路每天上午9点集合。" in context


#会话编号不同
def test_run_tool_chat_rejects_unknown_citation(monkeypatch):
    # 模拟知识库检索到的一条资料
    evidence = [{
        "chunk_id": "demo:chunk-1",
        "content": "示例线路每天上午9点集合。",
        "metadata": {
            "source_id": "S01",
            "source_title": "示例线路说明",
        },
    }]

    fake_execute = Mock(return_value={
        "ok": True,
        "data": {"evidence": evidence},
        "error": None,
    })
    monkeypatch.setattr(
        "app.tool_calling.execute_tool", fake_execute
    )

    # 模型第一次要求检索，第二次根据资料回答
    tool_call = {
        "id": "call_knowledge_1",
        "type": "function",
        "function": {
            "name": "knowledge_search",
            "arguments": '{"query": "示例线路几点集合？"}',
        },
    }

    fake_model = Mock(side_effect=[
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [tool_call],
        },
        {
            "role": "assistant",
            "content": json.dumps({
                "answer": "示例线路上午9点集合[999]。",
                "sources": ["999"],
            }, ensure_ascii=False),
        },
    ])
    monkeypatch.setattr(
        "app.tool_calling.call_tool_model", fake_model
    )

    result = run_tool_chat("示例线路几点集合？")

    assert result["answer"] == ""
    assert result["error"] == "模型引用了本轮不存在的编号：999"

    fake_execute.assert_called_once_with(
        "knowledge_search",
        {"query": "示例线路几点集合？"},
    )
    assert fake_model.call_count == 2


def test_run_tool_chat_reports_truncated_model_answer(monkeypatch, caplog):
    monkeypatch.setattr("app.tool_calling.load_dotenv", Mock())
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")

    fake_response = Mock()
    fake_response.json.return_value = {
        "choices": [{
            "finish_reason": "length",
            "message": {"role": "assistant", "content": '{"answer":'},
        }],
    }
    fake_post = Mock(return_value=fake_response)
    monkeypatch.setattr("app.tool_calling.requests.post", fake_post)

    result = run_tool_chat("请介绍旅行线路")

    assert result == {
        "answer": "",
        "error": "模型回答过长，未完整生成，请缩小问题范围后重试",
    }
    assert "模型回答因输出长度限制被截断" in caplog.text
    fake_post.assert_called_once()


def test_run_tool_chat_logs_invalid_knowledge_answer(monkeypatch, caplog):
    evidence = [{
        "chunk_id": "demo:chunk-1",
        "content": "示例线路每天上午9点集合。",
        "metadata": {},
    }]
    fake_execute = Mock(return_value={
        "ok": True,
        "data": {"evidence": evidence},
        "error": None,
    })
    monkeypatch.setattr("app.tool_calling.execute_tool", fake_execute)

    raw_answer = "这是没有JSON包装的回答。"
    fake_model = Mock(side_effect=[
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_knowledge_1",
                "type": "function",
                "function": {
                    "name": "knowledge_search",
                    "arguments": '{"query": "示例线路几点集合？"}',
                },
            }],
        },
        {"role": "assistant", "content": raw_answer},
    ])
    monkeypatch.setattr("app.tool_calling.call_tool_model", fake_model)

    result = run_tool_chat("示例线路几点集合？")

    assert result == {"answer": "", "error": "知识库回答格式不正确"}
    assert "知识库回答解析失败" in caplog.text
    assert raw_answer in caplog.text
    assert fake_model.call_count == 2


#测试资料摘要是否出现
@pytest.mark.parametrize("tool_name", ["web_search", "web_fetch"])
def test_run_tool_chat_returns_web_citations(monkeypatch, tool_name):
    url = "https://example.com/hotel"
    text = "酒店提供早餐。"

    if tool_name == "web_search":
        arguments = {"query": "测试酒店 早餐"}   #搜索“测试酒店 早餐
        tool_data = {
            "results": [{
                "title": "测试酒店",
                "url": url,
                "summary": text,
            }],
        }
        content_type = "搜索摘要"
    else:
        arguments = {"url": url}   #抓取这个网址
        tool_data = {
            "title": "测试酒店",
            "url": url,
            "content": text,
        }
        content_type = "网页正文"

    fake_execute = Mock(return_value={
        "ok": True,
        "data": tool_data,
        "error": None,
    })
    monkeypatch.setattr(
        "app.tool_calling.execute_tool", fake_execute
    )

    tool_call = {
        "id": "call_web_1",
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }

    fake_model = Mock(side_effect=[
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [tool_call],
        },
        {
            "role": "assistant",
            "content": json.dumps({
                "answer": "酒店提供早餐[1]。",
                "sources": ["1"],
            }, ensure_ascii=False),
        },
    ])
    monkeypatch.setattr(
        "app.tool_calling.call_tool_model", fake_model
    )

    result = run_tool_chat("查一下测试酒店是否提供早餐")

    assert result["error"] == ""
    assert result["answer"] == "酒店提供早餐[1]。"
    assert result["sources"] == ["1"]
    assert result["citations"] == [{
        "citation_id": "1",
        "chunk_id": f"{tool_name}:{url}",
        "metadata": {
            "source_type": "web",
            "source_title": "测试酒店",
            "url": url,
            "content_type": content_type,
        },
    }]
    assert result["evidence"][0]["content"] == text

    fake_execute.assert_called_once_with(tool_name, arguments)
    assert fake_model.call_count == 2
    assert fake_model.call_args.kwargs["json_mode"] is True

    messages = fake_model.call_args.args[0]
    tool_result = json.loads(messages[-1]["content"])
    context = tool_result["data"]["context"]

    assert url in context
    assert content_type in context
    assert text in context