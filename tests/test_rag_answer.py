from unittest.mock import patch
from app.rag_answer import generate_rag_answer


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

    fack_model_result={
        "answer": '{"answer": "午餐费用自理。", "sources": ["9"]}',
        "record": None,
        "error": "",
    }

    with patch(
        "app.rag_answer.call_model",
        return_value=fack_model_result,
    ):
        result=generate_rag_answer("午餐包含吗",context_result)

        assert result["error"]=="模型引用了未知资料编号：9"
        assert result["data"] is None
        assert result["citations"]==[]


def test_valid_citayion():
    history = [
    {"role": "user", "content": "我想吃鱼和鸡，推荐哪家？"},
    {"role": "assistant", "content": "可以考虑五庄·江浙菜（河坊街店）。"},
]
    context_result = {
        "context": "[1] 午餐费用自理。",
        "source_map": {
            "1": {
                "chunk_id": "test-chunk-1",
                "metadata": {},
            }
        },
    }

    fack_model_result={
        "answer": '{"answer": "午餐费用自理。", "sources": ["1"]}',
        "record": None,
        "error": "",
    }

    with patch(
        "app.rag_answer.call_model",
        return_value=fack_model_result,
    ) as mock_model:
        with patch(
            "app.rag_answer.rewrite_retrieval_question",
            return_value={"answer": "五庄·江浙菜（河坊街店）午餐包含吗？", "record": None, "error": ""},
        ) as mock_rewrite:
            result=generate_rag_answer("午餐包含吗",context_result,history)

    assert result["error"]==""
    assert result["data"]["sources"]==["1"]
    assert len(result["citations"])==1
    assert result["citations"][0]["citation_id"]=="1"
    assert result["citations"][0]["chunk_id"]=="test-chunk-1"
    mock_rewrite.assert_called_once_with("午餐包含吗", history)
    assert mock_model.call_args.kwargs["history"] is None
    assert mock_model.call_args.args[0] == "五庄·江浙菜（河坊街店）午餐包含吗？"


def test_resolved_question_uses_current_evidence_without_old_answers():
    history = [
        {"role": "user", "content": "之前另一个商品能退吗？"},
        {"role": "assistant", "content": "旧助手错误结论：前一天12点之后扣50%。"},
    ]
    context_result = {
        "context": "[1] 来源编号：S07；零点之后不可退。",
        "source_map": {"1": {"chunk_id": "s07-refund", "metadata": {"source_id": "S07"}}},
    }
    original_context = context_result["context"]
    fake_result = {"answer": '{"answer":"需核对订单适用条款。","sources":["1"]}', "record": None, "error": ""}
    with patch("app.rag_answer.call_model", return_value=fake_result) as mock_model:
        with patch("app.rag_answer.rewrite_retrieval_question") as mock_rewrite:
            result = generate_rag_answer(
                "我应该怎么回复？", context_result, history,
                retrieval_question="千岛湖套餐1出发当天凌晨1点取消能否退款？",
            )
    mock_rewrite.assert_not_called()
    assert result["error"] == ""
    assert mock_model.call_args.kwargs["history"] is None
    assert "旧助手错误结论" not in mock_model.call_args.kwargs["context"]
    assert "我应该怎么回复？" in mock_model.call_args.kwargs["context"]
    assert "来源编号：S07" in mock_model.call_args.kwargs["context"]
    assert "千岛湖套餐1" in mock_model.call_args.args[0]
    assert context_result["context"] == original_context


def test_failed_history_resolution_does_not_call_answer_model():
    context_result = {"context": "[1] 示例", "source_map": {"1": {"chunk_id": "one", "metadata": {}}}}
    with patch("app.rag_answer.rewrite_retrieval_question", return_value={
        "answer": "", "record": None, "error": "改写遗漏数字条件",
    }):
        with patch("app.rag_answer.call_model") as mock_model:
            result = generate_rag_answer("这个能退吗？", context_result, [{"role": "user", "content": "套餐1"}])
    assert "改写遗漏数字条件" in result["error"]
    assert result["data"] is None
    mock_model.assert_not_called()


def test_empty_resolved_question_does_not_call_answer_model():
    context_result = {"context": "[1] 示例", "source_map": {"1": {"chunk_id": "one", "metadata": {}}}}
    with patch("app.rag_answer.call_model") as mock_model:
        result = generate_rag_answer("这个能退吗？", context_result, retrieval_question=" ")
    assert result["error"] == "检索问题必须是非空字符串"
    mock_model.assert_not_called()
