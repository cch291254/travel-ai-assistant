from unittest.mock import patch

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
    assert result["error"] == "改写遗漏数字条件"
    assert result["pending_question"] == pending_question
    assert result["data"] is None
    assert result["record"] is None

    mock_retrieve.assert_not_called()
    mock_answer.assert_not_called()