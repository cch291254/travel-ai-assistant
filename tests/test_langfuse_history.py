import copy
from types import SimpleNamespace

import pytest

from examples import import_langfuse_history as history


@pytest.mark.parametrize("number,cases,turns,correct", [(1, 27, 29, 15), (2, 30, 40, 13), (3, 30, 40, 22)])
def test_original_counts_and_grading_are_preserved(number, cases, turns, correct):
    prepared = history.prepare_round(number)
    assert len(prepared["cases"]) == cases
    assert sum(len(case["original_rows"]) for case in prepared["cases"]) == turns
    assert sum(case["legacy_answer_correct"] for case in prepared["cases"]) == correct
    assert history.sha256(history.ROOT / "docs" / prepared["source_file"]) == prepared["source_sha256"]


def test_missing_and_skipped_turns_are_not_fabricated():
    cases = {case["case_id"]: case for case in history.prepare_round(1)["cases"]}
    assert len(cases["E07"]["input"]["questions"]) == 1
    assert cases["E03"]["output"]["turns"][1]["status"] == "skipped"
    assert cases["E03"]["output"]["turns"][1]["answer"] is None
    assert cases["E19"]["original_review_heading"] == "E019"


class DatasetItem(SimpleNamespace):
    def model_copy(self, *, update):
        cloned = copy.deepcopy(self)
        for key, value in update.items():
            setattr(cloned, key, value)
        return cloned


def test_upload_uses_old_answers_and_snapshots_without_overwriting_dataset(tmp_path, monkeypatch):
    prepared = history.prepare_round(1)
    old_case = next(case for case in prepared["cases"] if case["case_id"] == "E07")
    original = DatasetItem(id="travel-rag-v1-E07", metadata={"case_id": "E07", "turn_count": 2},
                           input={"questions": old_case["input"]["questions"] + ["later follow-up"]},
                           expected_output={"turns": [{"new-standard": True}]})
    before = copy.deepcopy(vars(original))
    calls = []

    class Client:
        api = SimpleNamespace(experiments=SimpleNamespace(list_items=lambda **kwargs: SimpleNamespace(data=[])))

        def get_dataset(self, name):
            return SimpleNamespace(items=[original])

        def run_experiment(self, **kwargs):
            item = kwargs["data"][0]
            assert item.input == old_case["input"]
            assert item.expected_output == old_case["expected_output"]
            output = kwargs["task"](item=item)
            assert output == old_case["output"]
            scores = kwargs["evaluators"][0](metadata=item.metadata)
            assert {s["name"]: s["value"] for s in scores}["legacy_answer_correct"] == 1
            calls.append(kwargs)
            result = SimpleNamespace(item=item, trace_id="history-trace", evaluations=scores, dataset_run_id="run-id")
            return SimpleNamespace(experiment_id="run-id", item_results=[result])

        def flush(self):
            pass

        def update_current_span(self, **kwargs):
            assert kwargs["metadata"]["original_run_info"] == prepared["original_run_info"]

    monkeypatch.setattr(history, "OUTPUT_DIR", tmp_path)
    history.upload_round(Client(), prepared, {"E07"})
    assert vars(original) == before
    assert len(calls) == 1
    assert list(tmp_path.glob("*receipt*.json"))


def test_existing_cloud_items_are_not_reimported(tmp_path, monkeypatch):
    prepared = history.prepare_round(1)
    item = DatasetItem(id="travel-rag-v1-E03", metadata={"case_id": "E03"})
    client = SimpleNamespace(
        get_dataset=lambda name: SimpleNamespace(items=[item]),
        api=SimpleNamespace(experiments=SimpleNamespace(list_items=lambda **kwargs:
            SimpleNamespace(data=[SimpleNamespace(experiment_item_id=item.id)]))),
        run_experiment=lambda **kwargs: pytest.fail("已有记录不应重复上传"),
    )
    monkeypatch.setattr(history, "OUTPUT_DIR", tmp_path)
    history.upload_round(client, prepared, {"E03"})
