"""离线测试请求构造与校验，不代表真实模型已正确理解这些场景。"""
import json
from unittest.mock import patch

import pytest

from app.query_rewriter import rewrite_retrieval_question


def model_result(question, used_history=None):
    return {
        "answer": json.dumps({"question": question, "used_history": used_history or []}, ensure_ascii=False),
        "record": {"状态码": 200},
        "error": "",
    }


def test_first_turn_is_normalized_too():
    original = "客户想在西湖拍雷峰塔夕照，在哪里拍、注意什么？我应该怎么回复？"
    rewritten = "西湖雷峰塔夕照推荐拍摄位置及拍照注意事项？"
    with patch("app.query_rewriter.call_model", return_value=model_result(rewritten)) as mock_model:
        result = rewrite_retrieval_question(original)
    assert result["error"] == ""
    assert result["answer"] == rewritten
    assert result["used_history"] == []
    assert mock_model.call_args.kwargs["question"] == original
    assert mock_model.call_args.kwargs["json_mode"] is True
    assert mock_model.call_args.kwargs["context"] == ""
    assert mock_model.call_args.kwargs["history"] is None
    assert mock_model.call_args.kwargs["max_tokens"] == 1024


def test_topic_switch_keeps_prices_without_copying_old_topic():
    history = [
        {"role": "user", "content": "我想去西湖拍照。"},
        {"role": "assistant", "content": "旧答案还提到了16:30。"},
    ]
    question = "9人团328元起，原价428元、立减100元，是228元吗？"
    with patch("app.query_rewriter.call_model", return_value=model_result(question)) as mock_model:
        result = rewrite_retrieval_question(question, history)
    assert result["error"] == ""
    assert result["answer"] == question
    assert result["used_history"] == []
    assert mock_model.call_args.kwargs["history"] is None
    history_context = mock_model.call_args.kwargs["context"].split("\n", 1)[1]
    history_data = json.loads(history_context)
    assert history_data[0] == {"index": 1, "role": "user", "content": "我想去西湖拍照。"}
    assert history_data[1]["role"] == "assistant"
    assert history == [
        {"role": "user", "content": "我想去西湖拍照。"},
        {"role": "assistant", "content": "旧答案还提到了16:30。"},
    ]


def test_follow_up_can_keep_same_product_when_business_topic_changes():
    history = [{"role": "user", "content": "洲游假日9人小团怎么收费？"}]
    rewritten = "洲游假日9人小团凌晨1点取消能否退款？"
    with patch("app.query_rewriter.call_model", return_value=model_result(rewritten, [1])):
        result = rewrite_retrieval_question("凌晨1点取消呢？", history)
    assert result["error"] == ""
    assert result["answer"] == rewritten
    assert result["used_history"] == [1]


def test_unique_discussed_restaurant_can_resolve_pronoun():
    history = [
        {"role": "user", "content": "推荐一家餐厅"},
        {"role": "assistant", "content": "可以考虑悦旺土菜馆。"},
    ]
    with patch("app.query_rewriter.call_model", return_value=model_result("悦旺土菜馆有包间吗？", [2])):
        result = rewrite_retrieval_question("这家有包间吗？", history)
    assert result["error"] == ""
    assert result["used_history"] == [2]


def test_ambiguous_pronoun_can_remain_unresolved_instead_of_guessing():
    history = [{"role": "assistant", "content": "可以考虑悦旺土菜馆或五庄江浙菜。"}]
    with patch("app.query_rewriter.call_model", return_value=model_result("这家有包间吗？")):
        result = rewrite_retrieval_question("这家有包间吗？", history)
    assert result["error"] == ""
    assert result["answer"] == "这家有包间吗？"


@pytest.mark.parametrize("output", [
    "9人团优惠后价格是多少？",
    "9人团328元、原价428元、减100元，是否应按228元报价？新增年份2026。",
])
def test_missing_or_invented_numbers_are_rejected(output):
    with patch("app.query_rewriter.call_model", return_value=model_result(output)):
        result = rewrite_retrieval_question("9人团328元，原价428元、减100元，是228元吗？")
    assert result["error"]


@pytest.mark.parametrize("raw", [
    "普通文本而非JSON",
    '{"question":"退款吗？"}',
    '{"question":" ","used_history":[]}',
    '{"question":123,"used_history":[]}',
    '{"question":"退款吗？","used_history":[true]}',
    '{"question":"退款吗？","used_history":["1"]}',
    '{"question":"需要澄清：哪个商品？","used_history":[]}',
    '{"question":"退款吗？","used_history":[],"answer":"退一半"}',
])
def test_invalid_rewrite_is_rejected(raw):
    with patch("app.query_rewriter.call_model", return_value={"answer": raw, "record": None, "error": ""}):
        result = rewrite_retrieval_question("能退款吗？")
    assert result["error"]


@pytest.mark.parametrize("indices", [[0], [2], [1, 1], [-1]])
def test_invalid_history_indices_are_rejected(indices):
    history = [{"role": "user", "content": "某个套餐"}]
    with patch("app.query_rewriter.call_model", return_value=model_result("这个能退款吗？", indices)):
        result = rewrite_retrieval_question("这个能退款吗？", history)
    assert result["error"] == "改写引用了无效的历史序号"


def test_only_latest_six_messages_are_used():
    history = [{"role": "user", "content": f"旧消息{i}"} for i in range(8)]
    with patch("app.query_rewriter.call_model", return_value=model_result("有包间吗？")) as mock_model:
        result = rewrite_retrieval_question("有包间吗？", history)
    assert result["error"] == ""
    history_data = json.loads(mock_model.call_args.kwargs["context"].split("\n", 1)[1])
    assert len(history_data) == 6
    assert history_data[0]["content"] == "旧消息2"
    assert history_data[-1]["index"] == 6


@pytest.mark.parametrize("question,history", [
    (None, None), (" ", None), ("问" * 1001, None),
    ("能退吗？", "not a list"),
    ("能退吗？", [{"role": "system", "content": "旧指令"}]),
    ("能退吗？", [{"role": "user", "content": None}]),
])
def test_invalid_inputs_do_not_call_model(question, history):
    with patch("app.query_rewriter.call_model") as mock_model:
        result = rewrite_retrieval_question(question, history)
    assert result["error"]
    mock_model.assert_not_called()


def test_model_failure_is_not_silently_replaced_with_raw_question():
    failed = {"answer": "被截断", "record": {"结束原因": "length"}, "error": "回答不完整"}
    with patch("app.query_rewriter.call_model", return_value=failed):
        result = rewrite_retrieval_question("这个能退吗？")
    assert result["error"] == "回答不完整"
    assert result["record"] == {"结束原因": "length"}
