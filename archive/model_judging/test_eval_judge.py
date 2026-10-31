import json
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock

import pytest
from pydantic import ValidationError

from app import eval_judge as judge
from examples import judge_langfuse_saved as runner


def material():
    return {"turns": [{"turn_number": 1, "question": "有包间吗？", "answer": "资料没有说明。",
                       "expected": {"points": ["说明包间未知"]}, "evidence": [], "citations": [], "error": None}]}


def judgment():
    return judge.CaseJudgment.model_validate({"turns": [{"turn_number": 1, "answer_coverage": 1,
        "coverage_reason": "回应了包间问题", "groundedness": 1,
        "groundedness_reason": "没有把资料未知说成肯定没有", "needs_review": False}]})


def test_inputs_use_actual_answers_and_original_criteria():
    output = {"turns": [{"turn_number": 1, "question": "有包间吗？", "result": {
        "answer": "资料没有说明。", "evidence": [{"chunk_id": "c1", "content": "位置和菜品",
            "metadata": {"source_id": "S02"}}]}}]}
    criteria = {"turns": [{"points": ["说明包间未知"], "forbidden_points": ["编造有包间"]}]}
    result = judge.build_judge_input(json.dumps(output), json.dumps(criteria))
    assert result["turns"][0]["answer"] == "资料没有说明。"
    assert result["turns"][0]["expected"] == criteria["turns"][0]
    assert result["turns"][0]["evidence"][0]["source_id"] == "S02"
    with pytest.raises(ValueError, match="轮数"):
        judge.build_judge_input(output, {"turns": []})


@pytest.mark.parametrize("bad", [0.7, -1, 2])
def test_invalid_scores_are_rejected(bad):
    value = judgment().model_dump()
    value["turns"][0]["answer_coverage"] = bad
    with pytest.raises(ValidationError):
        judge.CaseJudgment.model_validate(value)


@pytest.mark.parametrize("finish,number,error", [("length", 1, "截断"), ("stop", 2, "轮次")])
def test_truncated_or_wrong_turn_judgment_is_not_accepted(monkeypatch, finish, number, error):
    # 仅在无网络的测试中启用归档逻辑，验证原来的结果校验。
    monkeypatch.setattr(judge, "MODEL_JUDGING_ENABLED", True)
    value = judgment().model_dump()
    value["turns"][0]["turn_number"] = number
    response = Mock()
    response.json.return_value = {"choices": [{"finish_reason": finish,
        "message": {"content": json.dumps(value)}}]}
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-key")
    monkeypatch.setattr(judge.requests, "post", Mock(return_value=response))
    with pytest.raises(ValueError, match=error):
        judge.call_judge(material(), "test-model")


def test_cache_prevents_repeated_model_calls_and_human_review_keeps_model_score(tmp_path, monkeypatch):
    row = SimpleNamespace(trace_id="trace", id="observation", experiment_name="tool-agent-E03",
        metadata={"case_id": "E03"}, expected_output={"turns": [{"points": ["说明未知"]}]},
        output={"turns": [{"turn_number": 1, "question": "有包间吗？",
                           "result": {"answer": "资料没有说明。"}}]})
    generation = Mock()
    client = MagicMock()
    client.start_as_current_observation.return_value.__enter__.return_value = generation
    call = Mock(return_value=(judgment(), {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}))
    monkeypatch.setattr(runner, "RESULT_DIR", tmp_path)
    monkeypatch.setattr(runner, "call_judge", call)
    runner.review_saved(client, row)
    first_ids = [entry.kwargs["score_id"] for entry in client.create_score.call_args_list]
    runner.review_saved(client, row)
    assert call.call_count == 1
    assert [entry.kwargs["score_id"] for entry in client.create_score.call_args_list[2:]] == first_ids
    human_path = next(tmp_path.glob("*-human.json"))
    review = json.loads(human_path.read_text(encoding="utf-8"))
    review.update(answer_coverage=0.5, groundedness=1, reason="遗漏了一项，需要人工修正")
    human_path.write_text(json.dumps(review), encoding="utf-8")
    runner.review_saved(client, row, human_path)
    assert call.call_count == 1
    assert [entry.kwargs["name"] for entry in client.create_score.call_args_list[-2:]] == [
        "human_answer_coverage", "human_groundedness"]
    assert all(entry.kwargs["score_id"] not in first_ids for entry in client.create_score.call_args_list[-2:])


def test_quality_evaluator_can_be_attached_to_new_experiments(monkeypatch):
    from app import tracing
    client = MagicMock()
    monkeypatch.setattr(tracing, "get_tracing_client", lambda: client)
    call = Mock(return_value=(judgment(), {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}))
    monkeypatch.setattr(judge, "call_judge", call)
    scores = judge.evaluate_quality(
        output={"turns": [{"turn_number": 1, "question": "有包间吗？", "result": {"answer": "未知"}}]},
        expected_output={"turns": [{"points": ["说明未知"]}]}, metadata={"case_id": "E03"})
    assert [score["name"] for score in scores] == ["answer_coverage", "groundedness"]
    assert call.call_count == 1
    generation = client.start_as_current_observation.return_value.__enter__.return_value
    assert generation.update.call_args.kwargs["usage_details"]["total"] == 30


def test_disabled_judge_stops_before_any_model_request(monkeypatch):
    post = Mock()
    monkeypatch.setattr(judge.requests, "post", post)
    with pytest.raises(RuntimeError, match="已停用"):
        judge.call_judge(material(), "test-model")
    post.assert_not_called()
