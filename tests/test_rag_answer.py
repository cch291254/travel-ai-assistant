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
