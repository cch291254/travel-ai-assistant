from unittest.mock import patch

import pytest

from app.rag_pipeline import run_rag

#需要澄清时，提前返回，保存的问题不会被清成 None
def test_clarification_saves_question():
    question="晚上23:10下单，能保证30分钟内收到接车通知吗"
    history=[]

    fake_rewrite={
        "answer":question,
        "record": {"总tokens": 30},
        "error": "",
        "used_history": [],
        "sub_questions": [question],
        "needs_clarification": True,
        "clarification_question": "您预订的是哪个产品或套餐？",
        "target_source_ids": [],
    }

    with (patch(
        "app.rag_pipeline.rewrite_retrieval_question",
        return_value=fake_rewrite,
    ) as mock_rewrite,
    patch(
        "app.rag_pipeline.retrieve_evidence",
    ) as mock_retrieve,
    patch(
        "app.rag_pipeline.generate_rag_answer",
    ) as mock_answer,
    ):
        result = run_rag(
            question=question,
            history=history,
            model=None,
            collection=None,
            reranker=None,
        )

    # 检查改写函数收到的输入
    mock_rewrite.assert_called_once_with(question, history) 

    #检查澄清状态和追问内容
    assert result["error"] == ""
    assert result["needs_clarification"] is True
    assert result["pending_question"] == question
    assert result["data"] == {
        "answer": "您预订的是哪个产品或套餐？",
        "sources": [],
    }

    assert result["rewrite_record"]=={"总tokens":30}
    assert result["rewrite_result"] == fake_rewrite
    assert result["record"] is None
    assert result["evidence"]==[]
    assert result["citations"]==[]
    mock_retrieve.assert_not_called()
    mock_answer.assert_not_called()

#改写失败时，保留已有的待补充问题
def test_rewrite_error_preserves_pending_question():
    pending_question = "晚上23:10下单，能保证30分钟内收到接车通知吗？"
    question = "艾客旅游千岛湖套餐1"
    history = []

    fake_rewrite = {
    "answer": "",
    "record": {"总tokens": 30},
    "error": "改写遗漏数字条件",
}
    with (patch(
            "app.rag_pipeline.rewrite_retrieval_question",
            return_value=fake_rewrite,
        ) as mock_rewrite,
        patch(
            "app.rag_pipeline.retrieve_evidence",
        ) as mock_retrieve,
        patch(
            "app.rag_pipeline.generate_rag_answer",
        ) as mock_answer,
        ):
        result=run_rag(question,history,model=None,
    collection=None,
    reranker=None,pending_question=pending_question)

    expected_input = (
    pending_question
    + "\n用户补充信息："
    + question
)
    mock_rewrite.assert_called_once_with(expected_input, history)
    assert result["rewrite_record"] == {"总tokens": 30}
    assert result["rewrite_result"] == fake_rewrite
    assert result["error"] == "改写遗漏数字条件"
    assert result["pending_question"] == pending_question
    assert result["data"] is None
    assert result["record"] is None

    mock_retrieve.assert_not_called()
    mock_answer.assert_not_called()


#正常流程测试
@pytest.mark.parametrize(
    ("target_source_ids", "expected_where"),
    [
        (["S07"], {"source_id": {"$in": ["S07"]}}),
        ([], None),
    ],
    ids=["source-filter", "no-source-filter"],
)
@pytest.mark.parametrize("query_mode", ["split", "single", "duplicate"])
def test_successfu_run_rag(target_source_ids, expected_where, query_mode):
    pending_question = "这个套餐几点、在哪里集合？"
    question = "艾客旅游千岛湖套餐1"
    history = []
    full_question = "艾客旅游千岛湖套餐1几点、在哪里集合？"

    sub_questions = [
        "艾客旅游千岛湖套餐1的集合时间",
        "艾客旅游千岛湖套餐1的集合地点",
    ]
    if query_mode == "single":
        sub_questions = []
    elif query_mode == "duplicate":
        sub_questions.append(sub_questions[0])

    fake_rewrite={
        "answer": full_question,
        "record": {"总tokens": 30},
        "error": "",
        "used_history": [],
        "sub_questions": sub_questions,
        "needs_clarification": False,
        "clarification_question": "",
        "target_source_ids": target_source_ids,
    }

    chunk_a = {
        "chunk_id": "test-time",
        "content": "集合时间09:50。",
        "metadata": {"source_id": "S07"},
    }
    chunk_b = {
        "chunk_id": "test-place",
        "content": "在千岛湖中心湖区旅游码头集合。",
        "metadata": {"source_id": "S07"},
    }
    fake_model_result = {
        "answer": (
            '{"answer":"09:50在千岛湖中心湖区旅游码头集合。",'
            '"sources":["1","2"]}'
        ),
        "record": {"总tokens": 50},
        "error": "",
    }
    with (
        patch(
            "app.rag_pipeline.rewrite_retrieval_question",
            return_value=fake_rewrite,
        ) as mock_rewrite,
        patch(
            "app.rag_pipeline.retrieve_evidence",
            side_effect=[[chunk_a, chunk_b], [chunk_a], [chunk_b]],
        ) as mock_retrieve,
        patch(
            "app.rag_answer.call_model",
            return_value=fake_model_result,
        ) as mock_model,
    ):
        result = run_rag(
            question=question,
            history=history,
            model=None,
            collection=None,
            reranker=None,
            pending_question=pending_question,
        )

        rewrite_input=pending_question + "\n用户补充信息：" + question
        mock_rewrite.assert_called_once_with(rewrite_input,history)
        # 完整主问题始终参与检索，子问题去重后追加。
        expected_queries = (
            [full_question] if query_mode == "single" else [
                full_question,
                "艾客旅游千岛湖套餐1的集合时间",
                "艾客旅游千岛湖套餐1的集合地点",
            ]
        )
        assert mock_retrieve.call_count == len(expected_queries)
        for index,actual_call in enumerate(mock_retrieve.call_args_list):
            assert actual_call.args[0] == expected_queries[index]
            assert actual_call.kwargs == {
            "where": expected_where,
            "n_results": 7,
            "top_k": 3,
        }
        assert result["evidence"] == [chunk_a, chunk_b]
        assert result["error"] == ""
        assert result["needs_clarification"] is False
        assert result["pending_question"] is None

        assert result["data"] == {
        "answer": "09:50在千岛湖中心湖区旅游码头集合。",
        "sources": ["1", "2"],}
        assert result["citations"]==[
            {
            "citation_id": "1",
            "chunk_id": "test-time",
            "metadata": {"source_id": "S07"},
        },
        {
            "citation_id": "2",
            "chunk_id": "test-place",
            "metadata": {"source_id": "S07"},
        },
    ]
        assert result["rewrite_record"]=={"总tokens": 30}
        assert result["rewrite_result"] == fake_rewrite
        assert result["record"] == {"总tokens": 50}
        mock_model.assert_called_once()
        assert mock_model.call_args.args[0] == full_question
