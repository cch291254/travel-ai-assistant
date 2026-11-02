
import importlib.abc
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, Mock

import requests
import pytest
from app.tools import plan_search,trace_rewrite_usage

from app.tool_results import tool_result_to_json
from app.tools import (
    TOOL_CONTRACTS,
    TOOL_HANDLERS,
    calculate_accommodation,
    execute_tool,
    validate_search_input,
    build_model_tools,
    retrieve_routes,
    get_search_plan,
    search_state_var,
    confirmed_plan_search,
    owner_id_var,
)


@pytest.fixture  #这是一个测试准备函数
def fake_search(monkeypatch):
    resources = {"model": object(), "collection": object(), "reranker": object()}
    get_resources = Mock(return_value=resources)
    retrieve = Mock(return_value=[{
        "chunk_id": "test-1",
        "content": "住宿区域建议；并非已确认酒店价格。",
        "metadata": {"source_id": "TEST", "source_title": "测试资料"},
        "rerank_score": 0.8,
    }])
    resource_module = ModuleType("app.rag_resources")
    resource_module.get_rag_resources = get_resources
    retrieval_module = ModuleType("app.retrieval")
    retrieval_module.retrieve_evidence = retrieve
    monkeypatch.setitem(sys.modules, "app.rag_resources", resource_module)
    monkeypatch.setitem(sys.modules, "app.retrieval", retrieval_module)
    return resources, get_resources, retrieve


def room(room_type="双床房", rooms=2, nights=2, price="300.00"):
    return {
        "room_type": room_type, "rooms": rooms, "nights": nights,
        "room_night_price": price,
    }


def quote(**values):
    return execute_tool("calculate_quote", {"adults": 2, "children": 1, **values})

#测试名字
def test_contracts_match_handlers():
    assert set(TOOL_CONTRACTS) == set(TOOL_HANDLERS)
    assert TOOL_CONTRACTS["knowledge_search"]["parameters"]["required"] == ["query"]
    assert TOOL_CONTRACTS["calculate_quote"]["parameters"]["required"] == [
        "adults", "children",
    ]

#测试是否去掉空白
def test_search_validation_converts_defaults():
    assert validate_search_input(
        {"query": "  杭州住宿  "}
    )["data"] == {"query": "杭州住宿"}

#
@pytest.mark.parametrize("raw", [
    None, {}, [], {"query": "   "}, {"query": "x", "top_k": "3"},
    {"query": "x", "top_k": 0}, {"query": "x", "top_k": 11},
    {"query": "x", "extra": 1},
])
def test_invalid_search_does_not_load_resources(raw, fake_search):
    _, get_resources, retrieve = fake_search
    result = execute_tool("knowledge_search", raw)
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    get_resources.assert_not_called()
    retrieve.assert_not_called()


def test_search_passes_resources_and_counts(fake_search):
    resources, get_resources, retrieve = fake_search

    result = execute_tool(
        "knowledge_search",
        {"query": "  杭州住宿  "},
    )

    get_resources.assert_called_once_with()
    retrieve.assert_called_once_with(
        "杭州住宿",
        resources["model"],
        resources["collection"],
        resources["reranker"],
        where=None,
        n_results=7,
        top_k=3,
    )
    assert result["ok"] is True
    assert result["data"]["evidence"] == retrieve.return_value

def test_empty_search_is_success(fake_search):
    _, _, retrieve = fake_search
    retrieve.return_value = []
    assert execute_tool("knowledge_search", {"query": "没有匹配资料"}) == {
        "ok": True, "data": {"evidence": []}, "error": None,
    }


@pytest.mark.parametrize("stage", ["load", "retrieve"])
def test_search_errors_are_logged_and_wrapped(stage, fake_search, caplog):
    _, get_resources, retrieve = fake_search
    failing_function = get_resources if stage == "load" else retrieve
    failing_function.side_effect = RuntimeError("offline simulated failure")
    result = execute_tool("knowledge_search", {"query": "杭州住宿"})
    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"]["code"] == "RETRIEVAL_FAILED"
    assert "offline simulated failure" not in result["error"]["message"]
    assert "offline simulated failure" in caplog.text


def test_quote_sums_known_prices_and_multiple_rooms():
    result = quote(
        meal_price="50.00", transport_price="80.00", guide_price="20.00",
        ticket_price="0.00", room_items=[room(), room("大床房", 1, 2, "400.00")],
    )
    assert result["ok"] is True
    data = result["data"]
    assert data["person_costs"] == {
        "adult_base": Decimal("150.00"),
        "missing_items": ["boat_price", "entertainment_price"],
    }
    assert data["accommodation"] == {
        "known_total": Decimal("2000.00"), "missing_room_types": [],
    }
    assert data["requires_confirmation"] is True
    assert set(data) == {
    "person_costs", "child_costs",
    "adult_known_total", "child_known_total",
    "accommodation", "known_total",
    "requires_confirmation",
}

    assert data["adult_known_total"] == Decimal("300.00")
    assert data["child_known_total"] is None
    assert data["known_total"] == Decimal("2300.00")

def test_missing_room_price_preserves_partial_total():
    result = quote(room_items=[room(), room("大床房", 1, 2, None)])
    assert result["data"]["accommodation"] == {
        "known_total": Decimal("1200.00"), "missing_room_types": ["大床房"],
    }


def test_zero_room_price_is_not_missing():
    result = quote(room_items=[room(price="0.00")])
    assert result["data"]["accommodation"] == {
        "known_total": Decimal("0.00"), "missing_room_types": [],
    }


def test_unknown_accommodation_differs_from_no_accommodation():
    assert quote()["data"]["accommodation"] is None
    assert quote(room_items=None)["data"]["accommodation"] is None
    assert quote(room_items=[])["data"]["accommodation"] == {
        "known_total": Decimal("0.00"), "missing_room_types": [],
    }

#住宿费用错误
@pytest.mark.parametrize("rooms, nights", [(0, 0), (0, 2), (1, 0), (-1, 2), (1, -1)])
def test_invalid_accommodation_quantities(rooms, nights):
    result = quote(room_items=[room(rooms=rooms, nights=nights)])
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    assert "大于0" in result["error"]["message"]
    with pytest.raises(ValueError, match="大于0"):
        calculate_accommodation(room(rooms=rooms, nights=nights, price=None))

#输入错误
@pytest.mark.parametrize("values", [
    {"adults": 0}, {"adults": "2"}, {"children": -1},
    {"meal_price": "-1.00"}, {"meal_price": "1.123"},
    {"room_items": [room(price="-1.00")]},
    {"room_items": [room(price="1.123")]},
    {"room_items": [room(rooms="2")]},
    {"room_items": [room(room_type="   ")]}, {"extra": 1},
])
def test_quote_rejects_invalid_inputs(values):
    assert quote(**values)["error"]["code"] == "INVALID_ARGUMENT"

#未知工具错误
@pytest.mark.parametrize("name", ["unknown_tool", "", None, []])
def test_unknown_tool(name):
    assert execute_tool(name, {}) == {
        "ok": False, "data": None,
        "error": {"code": "UNKNOWN_TOOL", "message": "未知工具错误"},
    }


def test_json_serialization_preserves_calculation_types():
    result = quote(meal_price="50.00", room_items=[])
    text = tool_result_to_json(result)
    decoded = json.loads(text)
    assert decoded["data"]["person_costs"]["adult_base"] == "50.00"
    assert decoded["data"]["accommodation"]["known_total"] == "0.00"
    assert decoded["data"]["requires_confirmation"] is True
    assert decoded["error"] is None
    assert result["data"]["person_costs"]["adult_base"] == Decimal("50.00")


def test_import_and_quote_do_not_import_heavy_or_remote_modules():
    # 单独进程检查，避免其他测试已经导入模型模块而影响结果。
    code = '''
import importlib.abc
import sys

class NoExternalImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"torch", "sentence_transformers", "chromadb", "openai"}:
            raise AssertionError("Unexpected import: " + fullname)
        if fullname in {"app.rag_resources", "app.retrieval", "app.conversation_store", "app.api", "app.llm_client"}:
            raise AssertionError("Unexpected import: " + fullname)

sys.meta_path.insert(0, NoExternalImports())
from app.tools import execute_tool
assert execute_tool("calculate_quote", {"adults": 2, "children": 1})["ok"]
assert not execute_tool("knowledge_search", {"query": "   "})["ok"]
'''
    completed = subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr



#空搜索词提前返回,rejects拒绝，blank空白
def test_web_search_rejects_blank_query():
    result=execute_tool("web_search",{"query":"  "})

    assert result["ok"] is False
    assert result["error"]["code"]=="INVALID_ARGUMENT"


def test_web_search_returns_results(monkeypatch):
    monkeypatch.setattr("app.tools.load_dotenv",Mock())
    monkeypatch.setenv("DEEPSEEK_API_KEY","test-only-key")

    expected_results=[
        {
            "title":"测试网页",
            "url":"https://example.com",
            "summary":"测试摘要"
        }
    ]

    fake_response=Mock()
    fake_response.raise_for_status.return_value=None
    fake_response.json.return_value={     #规定调用 response.json() 时得到什么。
        "results":expected_results
    }
    fake_post=Mock(return_value=fake_response)
    monkeypatch.setattr("app.tools.requests.post",fake_post)  #将指定请求换成假的

    result=execute_tool("web_search",{"query":"西湖游船"})

    assert result["ok"] is True
    fake_post.assert_called_once()
    assert result["data"]["results"]==expected_results

#空值
def test_web_search_empty_results(monkeypatch):
    monkeypatch.setattr("app.tools.load_dotenv",Mock())
    monkeypatch.setenv("DEEPSEEK_API_KEY","test-only-key")

    expected_results=[]

    fake_response=Mock()
    fake_response.raise_for_status.return_value=None
    fake_response.json.return_value={     #规定调用 response.json() 时得到什么。
        "results":expected_results
    }
    fake_post=Mock(return_value=fake_response)
    monkeypatch.setattr("app.tools.requests.post",fake_post)  #将指定请求换成假的

    result=execute_tool("web_search",{"query":"西湖游船"})

    assert result["ok"] is True
    fake_post.assert_called_once()
    assert result["data"]["results"]==expected_results

#缺少密钥
def test_web_search_missing_key(monkeypatch):
    monkeypatch.setattr("app.tools.load_dotenv",Mock())
    monkeypatch.delenv("DEEPSEEK_API_KEY",raising=False)

    fake_post=Mock()
    monkeypatch.setattr("app.tools.requests.post",fake_post)

    result=execute_tool("web_search",{"query":"西湖游船"})

    assert result["ok"] is False
    assert result["error"]["code"]=="CONFIG_ERROR"
    fake_post.assert_not_called()

#超时返回
def test_web_search_timeout(monkeypatch):
    monkeypatch.setattr("app.tools.load_dotenv",Mock())
    monkeypatch.setenv("DEEPSEEK_API_KEY","test-pnly-key")

    fake_post=Mock(
        side_effect=requests.exceptions.Timeout("测试超时")
    )

    monkeypatch.setattr("app.tools.requests.post",fake_post)

    result=execute_tool("web_search",{"query":"西湖游船"})

    assert result["ok"] is False
    assert result["error"]["code"]=="SEARCH_TIMEOUT"
    fake_post.assert_called_once()
    assert fake_post.call_args.kwargs["json"] == {
    "query": "西湖游船",
    "count": 5,
}

#正常测试
def test_web_fetch_returns_page(monkeypatch):
    monkeypatch.setattr("app.tools.load_dotenv", Mock())
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")

    url = "https://example.com/article"

    fake_response = Mock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {
        "title": "测试网页",
        "content": "这是测试正文。",
    }

    fake_post = Mock(return_value=fake_response)
    monkeypatch.setattr("app.tools.requests.post", fake_post)

    result = execute_tool("web_fetch", {"url": url})

    assert result["ok"] is True
    assert result["data"] == {
        "url": url,
        "title": "测试网页",
        "content": "这是测试正文。",
    }
    fake_post.assert_called_once()
    assert fake_post.call_args.kwargs["json"] == {"url": url}


def test_web_fetch_rejects_empty_content(monkeypatch):
    monkeypatch.setattr("app.tools.load_dotenv", Mock())
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-key")

    url = "https://example.com/article"

    fake_response = Mock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {
        "title": "测试网页",
        "content": "  ",
    }

    fake_post = Mock(return_value=fake_response)
    monkeypatch.setattr("app.tools.requests.post", fake_post)

    result = execute_tool("web_fetch", {"url": url})

    assert result["ok"] is False
    assert result["error"]["code"] == "FETCH_BAD_RESPONSE"
    fake_post.assert_called_once()
    assert fake_post.call_args.kwargs["json"] == {"url": url}

#非法链接
def test_web_fetch_rejects_invalid_url(monkeypatch):
    fake_post = Mock()
    monkeypatch.setattr("app.tools.requests.post", fake_post)

    result = execute_tool("web_fetch", {"url": "not-a-url"})

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_ARGUMENT"
    fake_post.assert_not_called()

def test_web_fetch_timeout(monkeypatch):
    monkeypatch.setattr("app.tools.load_dotenv",Mock())
    monkeypatch.setenv("DEEPSEEK_API_KEY","test-pnly-key")

    fake_post=Mock(
        side_effect=requests.exceptions.Timeout("测试超时")
    )

    monkeypatch.setattr("app.tools.requests.post",fake_post)

    result=execute_tool("web_fetch",{"url": "https://example.com/article"},)

    assert result["ok"] is False
    assert result["error"]["code"]=="FETCH_TIMEOUT"
    fake_post.assert_called_once()
    assert fake_post.call_args.kwargs["json"] == {
    "url": "https://example.com/article"
}



def test_build_model_tools():
    tools = build_model_tools()

    assert len(tools) == len(TOOL_CONTRACTS)

    for item in tools:
        assert item["type"] == "function"
        function = item["function"]
        assert function["name"] in TOOL_CONTRACTS

    json.dumps(tools)   #json.dumps(tools) 检查这些说明能否转成 JSON




#这个测试为优化测试，儿童和成人计算区分
@pytest.mark.parametrize(
    "children, expected_child_total, expected_total",
    [
        (1, "60.00", "560.00"),
        (2, "120.00", "620.00"),
    ],
)
def test_quote_sums_adult_child_and_accommodation(
    children, expected_child_total, expected_total
):
    result = quote(
        adults=2,
        children=children,
        meal_price="100.00",
        child_prices={"meal_price": "60.00"},
        room_items=[room(rooms=1, nights=1, price="300.00")],
    )

    assert result["ok"] is True
    data = result["data"]

    assert data["person_costs"]["adult_base"] == Decimal("100.00")
    assert data["child_costs"]["child_base"] == Decimal("60.00")
    assert data["adult_known_total"] == Decimal("200.00")
    assert data["child_known_total"] == Decimal(expected_child_total)
    assert data["accommodation"]["known_total"] == Decimal("300.00")
    assert data["known_total"] == Decimal(expected_total)
    assert data["requires_confirmation"] is True


@pytest.mark.parametrize(
    "children, child_prices, expected_child_total",
    [
        (0, None, Decimal("0.00")),
        (1, None, None),
        (1, {"meal_price": "0.00"}, Decimal("0.00")),
    ],
)
def test_quote_child_price_boundaries(
    children, child_prices, expected_child_total
):
    result = quote(
        adults=2,
        children=children,
        meal_price="100.00",
        child_prices=child_prices,
        room_items=[],
    )

    assert result["ok"] is True
    data = result["data"]

    assert data["child_known_total"] == expected_child_total
    assert data["known_total"] == Decimal("200.00")

    if child_prices is None:
        assert data["child_costs"] is None
    else:
        assert data["child_costs"]["child_base"] == Decimal("0.00")
        assert "meal_price" not in data["child_costs"]["missing_items"]


def test_retrieve_routes_removes_duplicates(fake_search):
    resources, _, retrieve = fake_search
    retrieve.side_effect = [
        [{"chunk_id": "1"}, {"chunk_id": "2"}],
        [{"chunk_id": "2"}, {"chunk_id": "3"}],
    ]

    result = retrieve_routes(["a", "b"], resources)

    assert [item["chunk_id"] for item in result] == ["1", "2", "3"]
    assert retrieve.call_count == 2


#假冒重写
def fake_rewrite(**values):
    result = {
        "answer": "完整问题",
        "error": "",
        "sub_questions": [],
        "needs_clarification": False,
        "clarification_question": "",
        "target_source_ids": [],
    }
    result.update(values)
    return lambda question, history=None: result

#测试改写失败
def test_plan_search_keeps_query_when_rewrite_fails(monkeypatch):
    monkeypatch.setattr(
        "app.query_rewriter.rewrite_retrieval_question",
        fake_rewrite(error="改写失败"),
    )

    assert plan_search("原问题") == {
        "queries": ["原问题"], "where": None, "clarification": "",
    }


#测试澄清返回
def test_plan_search_returns_clarification(monkeypatch):
    monkeypatch.setattr(
        "app.query_rewriter.rewrite_retrieval_question",
        fake_rewrite(needs_clarification=True, clarification_question="是哪家商家？"),
    )

    assert plan_search("原问题")["clarification"] == "是哪家商家？"


#测试完整链路
def test_plan_search_builds_routes_and_filter(monkeypatch):
    monkeypatch.setattr(
        "app.query_rewriter.rewrite_retrieval_question",
        fake_rewrite(
            sub_questions=["完整问题", "子问题"],
            target_source_ids=["S05"],
        ),
    )

    plan = plan_search("原问题")

    assert plan["queries"] == ["完整问题", "子问题"]
    assert plan["where"] == {"source_id": {"$in": ["S05"]}}


def test_plan_search_without_target_searches_all(monkeypatch):
    monkeypatch.setattr(
        "app.query_rewriter.rewrite_retrieval_question",
        fake_rewrite(),
    )

    assert plan_search("原问题")["where"] is None



@pytest.fixture
def search_state():
    state = {"history": [], "searched": False, "where": None}
    token = search_state_var.set(state)
    yield state
    search_state_var.reset(token)


def test_search_plan_without_state_keeps_query():
    assert get_search_plan("原问题") == {
        "queries": ["原问题"], "where": None, "clarification": "",
    }


def test_search_plan_rewrites_only_first_search(monkeypatch, search_state):
    rewrite = Mock(side_effect=fake_rewrite(target_source_ids=["S05"]))
    monkeypatch.setattr("app.query_rewriter.rewrite_retrieval_question", rewrite)

    first = get_search_plan("第一次")
    second = get_search_plan("第二次")

    assert first["queries"] == ["完整问题"]
    assert second == {
        "queries": ["第二次"],
        "where": {"source_id": {"$in": ["S05"]}},
        "clarification": "",
    }
    rewrite.assert_called_once_with("第一次", history=[])



#测试问题澄清路线
def test_search_returns_clarification_without_loading(
    monkeypatch, fake_search, search_state,
):
    _, get_resources, _ = fake_search
    monkeypatch.setattr(
        "app.query_rewriter.rewrite_retrieval_question",
        fake_rewrite(needs_clarification=True, clarification_question="是哪家商家？"),
    )

    result = execute_tool("knowledge_search", {"query": "这个团多少钱"})

    assert result["data"] == {"clarification": "是哪家商家？"}
    get_resources.assert_not_called()


#测试资料不足补充新的切片
def test_search_retries_all_when_filter_finds_too_little(
    monkeypatch, fake_search, search_state,
):
    _, _, retrieve = fake_search  #元组拆包 ,只拿最后一个
    retrieve.side_effect = [
        [{"chunk_id": "1"}],
        [{"chunk_id": "1"}, {"chunk_id": "2"}],
    ]
    monkeypatch.setattr(
        "app.query_rewriter.rewrite_retrieval_question",
        fake_rewrite(target_source_ids=["S05"]),
    )

    result = execute_tool("knowledge_search", {"query": "S05 退款"})

    assert [item["chunk_id"] for item in result["data"]["evidence"]] == ["1", "2"]
    assert retrieve.call_args_list[0].kwargs["where"] == {"source_id": {"$in": ["S05"]}}
    assert retrieve.call_args_list[1].kwargs["where"] is None


#计算token
def test_rewrite_usage_is_traced(monkeypatch):
    client = MagicMock()
    generation = client.start_as_current_observation.return_value.__enter__.return_value
    monkeypatch.setattr("app.tracing.get_tracing_client", lambda: client)

    trace_rewrite_usage({
        "模型名": "demo", "输入tokens": 10, "输出tokens": 2, "总tokens": 12,
    })

    assert client.start_as_current_observation.call_args.kwargs["name"] == "model-call"
    generation.update.assert_called_once_with(
        usage_details={"input": 10, "output": 2, "total": 12},
    )


def test_rewrite_usage_skips_empty_record(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr("app.tracing.get_tracing_client", lambda: client)

    trace_rewrite_usage(None)

    client.start_as_current_observation.assert_not_called()


def test_model_tools_keep_price_fields_simple():
    quote_tool = next(
        item for item in build_model_tools()
        if item["function"]["name"] == "calculate_quote"
    )

    meal = quote_tool["function"]["parameters"]["properties"]["meal_price"]

    assert meal == {"type": "number", "description": "餐饮，元/成人"}


#只查自己的方案
def test_plan_search_only_reads_own_plans(monkeypatch, fake_search):
    resources, _, retrieve = fake_search
    plan_collection = object()
    monkeypatch.setattr("app.plan_index.get_plan_collection", lambda: plan_collection)
    token = owner_id_var.set("user_a")
    try:
        result = confirmed_plan_search({"query": "杭州两日游"})
    finally:
        owner_id_var.reset(token)

    assert result["ok"] is True
    assert retrieve.call_args.args[2] is plan_collection
    assert retrieve.call_args.kwargs["where"] == {"owner_id": "user_a"}


#没有身份拒绝
def test_plan_search_needs_owner(fake_search):
    _, _, retrieve = fake_search

    result = confirmed_plan_search({"query": "杭州两日游"})

    assert result["error"]["code"] == "NO_OWNER"
    retrieve.assert_not_called()