from examples import build_eval_report as report


def make_case(case_id="E01", *, source_ids=("S01",), found=("S01",), needs_clarification=False,
              scores=None):
    result = {
        "answer": "回答",
        "error": "",
        "evidence": [{"metadata": {"source_id": source_id}} for source_id in found],
    }
    return {
        "case_id": case_id,
        "trace_id": f"trace-{case_id}",
        "expected_output": {"turns": [{
            "source_ids": list(source_ids),
            "needs_clarification": needs_clarification,
        }]},
        "output": {"turns": [{"result": result, "elapsed_seconds": 2.0}]},
        "scores": scores or [
            {"name": "execution_complete", "value": 1},
            {"name": "source_coverage", "value": 1.0},
        ],
    }


def human(coverage, groundedness, comment=None):
    return {
        report.HUMAN_COVERAGE: {"value": coverage, "comment": comment},
        report.HUMAN_GROUNDEDNESS: {"value": groundedness, "comment": None},
    }


#预期来源只找到一部分，不算完整命中
def test_partial_evidence_is_not_a_complete_hit():
    case = make_case(source_ids=("S01", "S02"), found=("S01",))

    summary = report.summarize_case(case)

    assert summary["evidence_hits"] == 0
    assert summary["rows"][0]["matched"] == 1


#应该反问的轮次不检索，不进入证据命中的分母
def test_clarification_turn_skips_evidence():
    case = make_case(source_ids=("S01",), found=(), needs_clarification=True)

    assert report.summarize_case(case)["evidence_rows"] == []


#未执行的轮次要保留，不能让分母变小
def test_missing_turn_counts_as_miss():
    case = make_case(found=())
    case["output"] = None

    summary = report.summarize_case(case)

    assert len(summary["evidence_rows"]) == 1
    assert summary["evidence_hits"] == 0


#反问效果只统计含反问轮次的题，并以人工要点覆盖为准
def test_clarification_uses_human_coverage():
    summaries = [
        report.summarize_case(make_case("E07", needs_clarification=True), human(0, 1)),
        report.summarize_case(make_case("E01"), human(1, 1)),
    ]

    rows = {row[0]: row[1] for row in report.overall_rows(summaries)}

    assert rows["反问题要点覆盖"] == "0.00"


#幻觉率只看已评分的题，未评分不能当作 0 分
def test_hallucination_rate_ignores_unscored_cases():
    summaries = [
        report.summarize_case(make_case("E01"), human(1, 0)),
        report.summarize_case(make_case("E02"), human(1, 1)),
        report.summarize_case(make_case("E04")),
    ]

    rows = {row[0]: row[1] for row in report.overall_rows(summaries)}

    assert rows["幻觉率"] == "1/2（50.00%）"


def test_attention_case_and_attribution():
    good = report.summarize_case(make_case("E01"), human(1, 1))
    bad = report.summarize_case(make_case("E02"), human(0.5, 1, "检索：报价段没有进入证据"))

    assert report.is_attention_case(good) is False
    assert report.is_attention_case(bad) is True
    assert report.attribution_counts([good, bad]) == {"检索": 1}


def test_build_report_groups_cases():
    run = {"run_name": "测试运行", "results": [make_case("E01"), make_case("E10")]}
    scores = {"trace-E01": human(1, 1), "trace-E10": human(0.5, 0, "工具：价格算错")}

    text = report.build_report(run, scores)

    assert "知识、政策与行程" in text
    assert "多条件推荐、报价与集合" in text
    assert "工具：价格算错" in text
    assert "1/2（50.00%）" in text


def test_find_latest_run_skips_usage_file(tmp_path):
    (tmp_path / "20261028T01.json").write_text("{}", encoding="utf-8")
    (tmp_path / "20261029T01.json").write_text("{}", encoding="utf-8")
    (tmp_path / "20261030T01-usage.json").write_text("{}", encoding="utf-8")

    assert report.find_latest_run(tmp_path).name == "20261029T01.json"


def test_issue_type_prefers_execution_errors():
    failed = make_case("E16", found=(), scores=[{"name": "execution_complete", "value": 0}])
    failed["output"]["turns"][0]["result"]["error"] = "知识库回答格式不正确"
    limited = make_case("E10", found=(), scores=[{"name": "execution_complete", "value": 0}])
    limited["output"]["turns"][0]["result"]["error"] = "已达到模型请求轮数上限，请缩小问题后重试"

    assert report.issue_type(report.summarize_case(failed)) == "回答格式"
    assert report.issue_type(report.summarize_case(limited)) == "工具循环"
    assert report.issue_type(report.summarize_case(make_case("E19", found=()))) == "证据未命中"


def test_review_lists_raw_answer_and_trace():
    case = make_case("E16", found=(), scores=[{"name": "execution_complete", "value": 0}])
    case["output"]["turns"][0]["question"] = "问题"
    case["output"]["turns"][0]["result"].update(error="知识库回答格式不正确", raw_answer="坏的原文")

    text = report.build_review({"run_name": "测试运行", "results": [case]})

    assert "## 回答格式（1 题）" in text
    assert "坏的原文" in text
    assert report.TRACE_URL + "trace-E16" in text
