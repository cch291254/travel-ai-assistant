"""验证批量评测入口，不调用真实模型，不读取向量库。"""
import json
import re
from unittest.mock import Mock

from examples import run_rag_eval as evaluation


def test_main_runs_all_cases_and_saves_timestamped_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "examples").mkdir()
    cases = [
        {
            "id": f"E{index:02d}",
            "turns": [{
                "question": f"测试问题{index}",
                "expected_needs_clarification": False,
                "expected_source_ids": [],
                "expected_points": [],
                "forbidden_points": [],
            }],
        }
        for index in range(1, 31)
    ]
    caller = Mock(return_value={
        "data": {"answer": "模拟回答", "sources": []},
        "error": "",
        "needs_clarification": False,
        "pending_question": None,
    })
    monkeypatch.setattr(evaluation, "load_eval_cases", lambda path: cases)
    monkeypatch.setattr(evaluation, "real_model_caller", caller)
    monkeypatch.setattr(evaluation, "load_dotenv", lambda: None)
    monkeypatch.setattr(evaluation, "collect_version_hashes", lambda: {"test": "hash"})
    monkeypatch.setenv("DEEPSEEK_MODEL", "test-model")

    evaluation.main()

    paths = list((tmp_path / "examples").glob("rag_eval_results_*.json"))
    assert len(paths) == 1
    assert re.fullmatch(r"rag_eval_results_\d{8}_\d{6}_\d{6}\.json", paths[0].name)
    report = json.loads(paths[0].read_text(encoding="utf-8"))
    assert caller.call_count == 30
    assert report["run_info"]["selected_case_ids"] == [case["id"] for case in cases]
    assert report["run_info"]["collection"] == "travel_documents_full_20161014_v2"
    assert report["run_info"]["retrieval_n_results_per_query"] == 7
    assert report["run_info"]["rerank_top_k_per_query"] == 3
    assert report["run_info"]["model"] == "test-model"
    assert len(report["results"]) == 30
    assert all(item["status"] == "ok" for item in report["results"])
