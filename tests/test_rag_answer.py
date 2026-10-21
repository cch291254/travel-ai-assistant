import json
from unittest.mock import patch

import pytest

from app.rag_answer import RAG_SYSTEM_PROMPT, generate_rag_answer
from app.rag_context import build_context


@pytest.fixture(autouse=True)
def forbid_real_http(monkeypatch):
    def fail_request(*args, **kwargs):
        raise AssertionError("引用单元测试禁止真实HTTP请求")

    monkeypatch.setattr("requests.sessions.Session.request", fail_request)


def test_no_evidence_skips_model():
    context_result={
        "context":"",
        "source_map":{}
    }

    with patch("app.rag_answer.call_model") as mock_model:
        result=generate_rag_answer("午餐包含吗",context_result)

    assert result["error"] == ""
    assert "未检索到" in result["data"]["answer"]
    assert result["data"]["sources"] == []
    assert result["citations"] == []
    mock_model.assert_not_called()

def test_unkown_citation_is_rejected():
    context_result = {
        "context": "[1] 午餐费用自理。",
        "source_map": {
            "1": {
                "chunk_id": "test-chunk-1",
                "metadata": {},
            }
        },
    }

    fake_model_result={
        "answer": '{"answer": "午餐费用自理。", "sources": ["9"]}',
        "record": None,
        "error": "",
    }

    with patch(
        "app.rag_answer.call_model",
        return_value=fake_model_result,
    ):
        result=generate_rag_answer("午餐包含吗",context_result)

        assert result["error"]=="模型引用了未知资料编号：9"
        assert result["raw_answer"] == fake_model_result["answer"]
        assert result["data"] is None
        assert result["citations"]==[]



def test_valid_citation():
     # 1. 准备：模拟检索上下文和模型返回
    context_result = {
        "context": "[1] 午餐费用自理。",
        "source_map": {
            "1": {
                "chunk_id": "test-chunk-1",
                "metadata": {"source_id": "S07"},
            }
        },
    }

    fake_model_result={
        "answer": '{"answer": "午餐费用自理。", "sources": ["1"]}',
        "record": {"总tokens":15},
        "error": "",
    }
# 2. 执行：替换真实模型调用，不发出网络请求
    with patch(
        "app.rag_answer.call_model",
        return_value=fake_model_result,
    ) as mock_model:
            result=generate_rag_answer("这个套餐午餐包含吗",context_result,retrieval_question="千岛湖套餐1午餐包含吗")

    assert result["error"]==""
    assert result["citations"][0]["chunk_id"]=="test-chunk-1"
    assert result["record"]=={"总tokens":15}
    assert result["data"] == {
        "answer": "午餐费用自理。",
        "sources": ["1"],
    }
    assert result["citations"] == [
        {
            "citation_id": "1",
            "chunk_id": "test-chunk-1",
            "metadata": {"source_id": "S07"},
        }
    ]
    assert mock_model.call_args.kwargs["history"] is None
    assert mock_model.call_args.args[0] == "千岛湖套餐1午餐包含吗"
    mock_model.assert_called_once()


# 检查完整问题的传递，以及上下文的保留
def test_resolved_question_preserves_context():
    context_result={
        "context": "[1] 来源编号：S07；零点之后不可退。",
        "source_map": {
            "1": {
                "chunk_id": "s07-refund",
                "metadata": {"source_id": "S07"},
    }}}
    original_context=context_result["context"]
    full_question="千岛湖套餐1出发当天凌晨1点取消能否退款？"

    fake_result={
        "answer":'{"answer":"需核对订单适用条款。","sources":["1"]}',
        "record": None,
        "error": "",
    }

    with patch(
        "app.rag_answer.call_model",
        return_value=fake_result,
    ) as mock_model:
        result=generate_rag_answer(
            "我应该怎么回复",
            context_result,
            retrieval_question=full_question,
        )

    assert result["error"]==""
    mock_model.assert_called_once()
    assert mock_model.call_args.args[0]==full_question
    sen_context=mock_model.call_args.kwargs["context"]
    assert "我应该怎么回复" in sen_context
    assert original_context in sen_context
    assert mock_model.call_args.kwargs["history"] is None
    assert context_result["context"]== original_context

    

#模型错误返回
def test_model_error_is_returned():
    context_result = {
        "context": "[1] 示例资料",
        "source_map": {
            "1": {
                "chunk_id": "test-chunk-1",
                "metadata": {},
            }
        },
    }
    fake_result = {
        "answer": "",
        "record": {"状态码": 503},
        "error": "模型服务暂时不可用",
    }
    with patch(
        "app.rag_answer.call_model", 
        return_value=fake_result,
        )as mock_model:
            result = generate_rag_answer(
                "午餐包含吗？", 
                context_result)
    assert result["error"]=="模型服务暂时不可用"
    assert result["record"]=={"状态码":503}
    assert result["data"] is None
    assert result["citations"]==[]
    mock_model.assert_called_once()

def test_empty_resolved_question_does_not_call_answer_model():
    context_result = {"context": "[1] 示例", "source_map": {"1": {"chunk_id": "one", "metadata": {}}}}
    with patch("app.rag_answer.call_model") as mock_model:
        result = generate_rag_answer("这个能退吗？", context_result, retrieval_question=" ")
    assert result["error"] == "检索问题必须是非空字符串"
    mock_model.assert_not_called()


def test_prompt_lists_actual_current_citation_ids():
    context_result = {
        "context": "[2] 第一片。\n[7] 第二片。",
        "source_map": {
            "2": {"chunk_id": "first", "metadata": {"source_id": "S02"}},
            "7": {"chunk_id": "second", "metadata": {"source_id": "SIM01"}},
        },
    }
    fake_result = {
        "answer": '{"answer":"第一片支持回答。","sources":["2"]}',
        "record": None,
        "error": "",
    }
    original_prompt = RAG_SYSTEM_PROMPT

    with patch("app.rag_answer.call_model", return_value=fake_result) as mock_model:
        result = generate_rag_answer("测试问题", context_result)

    assert result["error"] == ""
    prompt = mock_model.call_args.kwargs["system_prompt"]
    assert '本轮sources允许选择的引用编号：["2", "7"]' in prompt
    assert "S02、S03、SIM01等来源标识" in prompt
    assert "均不能填入sources" in prompt
    assert RAG_SYSTEM_PROMPT == original_prompt
    assert "本轮sources允许选择的引用编号" not in RAG_SYSTEM_PROMPT
    assert list(context_result["source_map"]) == ["2", "7"]


@pytest.mark.parametrize("source_id", ["S02", "S03", "SIM01"])
def test_source_id_is_rejected_without_guessing_a_chunk(source_id):
    context_result = build_context([
        {"chunk_id": "one", "content": "第一片。", "metadata": {"source_id": source_id}},
        {"chunk_id": "two", "content": "第二片。", "metadata": {"source_id": source_id}},
    ])
    fake_result = {
        "answer": json.dumps({"answer": "测试回答。", "sources": [source_id]}, ensure_ascii=False),
        "record": None,
        "error": "",
    }

    with patch("app.rag_answer.call_model", return_value=fake_result):
        result = generate_rag_answer("测试问题", context_result)

    assert result["error"] == f"模型引用了未知资料编号：{source_id}"
    assert result["data"] is None
    assert result["citations"] == []


def test_two_chunks_from_one_source_keep_distinct_citations():
    context_result = build_context([
        {"chunk_id": "photo-position", "content": "拍摄位置。", "metadata": {"source_id": "S03"}},
        {"chunk_id": "photo-safety", "content": "临水安全。", "metadata": {"source_id": "S03"}},
    ])
    fake_result = {
        "answer": '{"answer":"拍摄时注意临水安全。","sources":["1","2"]}',
        "record": None,
        "error": "",
    }

    with patch("app.rag_answer.call_model", return_value=fake_result):
        result = generate_rag_answer("在哪拍、注意什么？", context_result)

    assert result["error"] == ""
    assert result["data"]["sources"] == ["1", "2"]
    assert [item["chunk_id"] for item in result["citations"]] == ["photo-position", "photo-safety"]
    assert all(item["metadata"]["source_id"] == "S03" for item in result["citations"])


def test_empty_sources_are_allowed_when_evidence_does_not_support_answer():
    context_result = build_context([
        {"chunk_id": "menu", "content": "仅有菜品推荐。", "metadata": {"source_id": "S02"}},
    ])
    fake_result = {
        "answer": '{"answer":"资料未提供包间信息。","sources":[]}',
        "record": None,
        "error": "",
    }

    with patch("app.rag_answer.call_model", return_value=fake_result):
        result = generate_rag_answer("有没有包间？", context_result)

    assert result["error"] == ""
    assert result["data"]["sources"] == []
    assert result["citations"] == []


def test_allowed_citation_ids_are_rebuilt_for_each_call():
    prompts = []
    fake_result = {"answer": '{"answer":"信息不足。","sources":[]}', "record": None, "error": ""}

    with patch("app.rag_answer.call_model", return_value=fake_result) as mock_model:
        for citation_id in ["1", "8"]:
            context_result = {
                "context": f"[{citation_id}] 测试片段。",
                "source_map": {citation_id: {"chunk_id": citation_id, "metadata": {}}},
            }
            result = generate_rag_answer("测试问题", context_result)
            assert result["error"] == ""
            prompts.append(mock_model.call_args.kwargs["system_prompt"])

    assert '本轮sources允许选择的引用编号：["1"]' in prompts[0]
    assert '本轮sources允许选择的引用编号：["8"]' in prompts[1]
    assert '本轮sources允许选择的引用编号：["1"]' not in prompts[1]
