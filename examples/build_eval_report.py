"""把一次评测运行汇总成 Markdown 报告；不运行助手，不请求模型，可以反复执行。

规则分、证据和耗时读取 examples/evaluation_runs/ 的运行文件；人工分和 Token 读取 Langfuse。

    python -m examples.build_eval_report --proxy http://127.0.0.1:7897
    python -m examples.build_eval_report --run 运行文件路径 --offline

人工分的备注以“检索：”“重排：”“生成：”“工具：”开头时，报告会按这四类统计问题归因。
"""
import argparse
import json
import os
from collections import Counter
from pathlib import Path
from statistics import mean, median

from app.tracing import get_tracing_client, setup_tracing, shutdown_tracing


RUN_DIR = Path(__file__).resolve().parent / "evaluation_runs"
HUMAN_COVERAGE = "human_answer_coverage"
HUMAN_GROUNDEDNESS = "human_groundedness"
ATTRIBUTIONS = ("检索", "重排", "生成", "工具")
SCORE_FIELDS = "details"

# 沿用第二、三轮评审的互斥题型分组，新旧报告可以按题型对照。
CASE_GROUPS = {
    "知识、政策与行程": ["E01", "E02", "E04", "E05", "E06", "E08"],
    "多条件推荐、报价与集合": ["E10", "E12", "E13", "E14", "E15", "E16", "E25", "E26"],
    "过期与版本": ["E17", "E18", "E19"],
    "冲突判断": ["E20", "E21", "E22", "E27"],
    "原有多轮": ["E03", "E11"],
    "产品澄清": ["E07", "E09"],
    "无答案": ["E23", "E24"],
    "新增多轮": ["E28", "E29", "E30"],
    "工具计算": ["E31", "E32", "E33", "E34", "E35"],
    "网络搜索与抓取": ["E36", "E37", "E38", "E39", "E40"],
}


def group_of(case_id):
    return next((name for name, ids in CASE_GROUPS.items() if case_id in ids), "未分组")


def find_latest_run(run_dir=RUN_DIR):
    """运行文件名以时间开头，排序后最后一个就是最新结果；用量文件不算运行结果。"""
    runs = sorted(path for path in run_dir.glob("*.json") if not path.stem.endswith("-usage"))
    if not runs:
        raise FileNotFoundError(f"{run_dir} 中没有运行结果")
    return runs[-1]


def ratio(matched, total):
    return f"{matched}/{total}（{matched / total:.2%}）" if total else "不适用"


def average(values):
    """缺失的分数不计入平均，也不能当作 0 分。"""
    known = [value for value in values if value is not None]
    return mean(known) if known else None


def score_text(value):
    return "未评分" if value is None else f"{value:.2f}"


def evidence_source_ids(result):
    """进入最终证据的来源编号；和 citations 不同，这里看的是检索有没有找到。"""
    items = result.get("evidence") or []
    source_ids = {(item.get("metadata") or {}).get("source_id") for item in items}
    source_ids.discard(None)
    return source_ids


def turn_rows(case):
    """逐轮整理证据、反问和耗时；未执行的轮次也保留，避免分母变小。"""
    turns = (case.get("output") or {}).get("turns") or []
    rows = []
    for index, expected in enumerate(case["expected_output"]["turns"]):
        actual = turns[index] if index < len(turns) else {}
        result = actual.get("result") or {}
        expected_ids = set(expected.get("source_ids") or [])
        needs_clarification = bool(expected.get("needs_clarification"))
        rows.append({
            "required": len(expected_ids),
            "matched": len(expected_ids & evidence_source_ids(result)),
            # 应该反问的轮次不检索，不计入证据命中。
            "evidence_applicable": bool(expected_ids) and not needs_clarification,
            "needs_clarification": needs_clarification,
            "elapsed": actual.get("elapsed_seconds"),
        })
    return rows


def rule_score(case, name):
    return next((score["value"] for score in case.get("scores") or [] if score["name"] == name), None)


def summarize_case(case, langfuse_data=None):
    langfuse_data = langfuse_data or {}
    rows = turn_rows(case)
    evidence_rows = [row for row in rows if row["evidence_applicable"]]
    coverage = langfuse_data.get(HUMAN_COVERAGE) or {}
    groundedness = langfuse_data.get(HUMAN_GROUNDEDNESS) or {}
    return {
        "case_id": case["case_id"],
        "group": group_of(case["case_id"]),
        "rows": rows,
        "evidence_rows": evidence_rows,
        "evidence_hits": sum(row["matched"] == row["required"] for row in evidence_rows),
        "needs_clarification": any(row["needs_clarification"] for row in rows),
        "execution_complete": rule_score(case, "execution_complete"),
        "source_coverage": rule_score(case, "source_coverage"),
        "human_coverage": coverage.get("value"),
        "human_groundedness": groundedness.get("value"),
        "comments": [text for text in (coverage.get("comment"), groundedness.get("comment")) if text],
        "tokens": langfuse_data.get("tokens"),
    }


def is_attention_case(summary):
    """有任意一项没达标，就进入需要复盘的清单。"""
    checks = (
        summary["execution_complete"] == 1,
        summary["evidence_hits"] == len(summary["evidence_rows"]),
        summary["source_coverage"] in (None, 1, 1.0),
        summary["human_coverage"] in (None, 1, 1.0),
        summary["human_groundedness"] in (None, 1, 1.0),
    )
    return not all(checks)


def attribution_counts(summaries):
    counts = Counter()
    for summary in summaries:
        for comment in summary["comments"]:
            label = comment.split("：", 1)[0].strip()
            if label in ATTRIBUTIONS:
                counts[label] += 1
    return counts


def overall_rows(summaries):
    rows = [row for summary in summaries for row in summary["rows"]]
    evidence_rows = [row for summary in summaries for row in summary["evidence_rows"]]
    evidence_hits = sum(summary["evidence_hits"] for summary in summaries)
    clarification = [summary for summary in summaries if summary["needs_clarification"]]
    clarification_scored = [summary["human_coverage"] for summary in clarification if summary["human_coverage"] is not None]
    elapsed = [row["elapsed"] for row in rows if row["elapsed"] is not None]
    tokens = [summary["tokens"] for summary in summaries if summary["tokens"] is not None]
    coverage = [summary["human_coverage"] for summary in summaries if summary["human_coverage"] is not None]
    groundedness = [summary["human_groundedness"] for summary in summaries if summary["human_groundedness"] is not None]
    executed = sum(summary["execution_complete"] == 1 for summary in summaries)
    source_scores = average(summary["source_coverage"] for summary in summaries)

    return [
        ("执行成功率", ratio(executed, len(summaries)), "所有轮次完成且没有错误"),
        ("证据完整命中率", ratio(evidence_hits, len(evidence_rows)), "预期来源全部进入最终证据的轮次"),
        ("引用覆盖率", score_text(source_scores), "预期来源被回答引用的比例，有来源要求的题取平均"),
        ("要点覆盖率", score_text(average(coverage)), f"人工分平均，已评 {len(coverage)}/{len(summaries)} 题"),
        ("平均依据分", score_text(average(groundedness)), f"人工分平均，已评 {len(groundedness)}/{len(summaries)} 题"),
        ("幻觉率", ratio(sum(value == 0 for value in groundedness), len(groundedness)), "依据分为 0 的题占已评题数"),
        ("反问题要点覆盖", score_text(average(clarification_scored)), f"含应先反问轮次的题，已评 {len(clarification_scored)}/{len(clarification)} 题"),
        ("平均耗时", f"{mean(elapsed):.2f} 秒" if elapsed else "未记录", f"中位数 {median(elapsed):.2f} 秒，最长 {max(elapsed):.2f} 秒" if elapsed else ""),
        ("平均 Token", f"{mean(tokens):.0f}/题" if tokens else "未记录", f"已读取 {len(tokens)}/{len(summaries)} 题"),
    ]


def group_rows(summaries):
    rows = []
    for name in [*CASE_GROUPS, "未分组"]:
        members = [summary for summary in summaries if summary["group"] == name]
        if not members:
            continue
        evidence_total = sum(len(summary["evidence_rows"]) for summary in members)
        evidence_hits = sum(summary["evidence_hits"] for summary in members)
        groundedness = [summary["human_groundedness"] for summary in members if summary["human_groundedness"] is not None]
        rows.append((
            name, len(members), ratio(evidence_hits, evidence_total),
            score_text(average(summary["human_coverage"] for summary in members)),
            ratio(sum(value == 0 for value in groundedness), len(groundedness)) if groundedness else "未评分",
        ))
    return rows


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + " --- |" * len(headers)]
    lines += ["| " + " | ".join(str(cell).replace("|", "\\|").replace("\n", " ") for cell in row) + " |" for row in rows]
    return lines


def build_report(run, langfuse_scores=None):
    langfuse_scores = langfuse_scores or {}
    summaries = [summarize_case(case, langfuse_scores.get(case["trace_id"])) for case in run["results"]]
    hashes = run.get("code_hashes") or {}
    lines = [
        "# 评测基线报告",
        "",
        "## 运行信息",
        "",
        f"- 运行名称：{run.get('run_name', '未记录')}",
        f"- 代码提交：{run.get('git_commit', '未记录')}",
        f"- 题目数量：{len(summaries)} 题，{sum(len(summary['rows']) for summary in summaries)} 轮",
        f"- 文件哈希：{'；'.join(f'{name} {value[:12]}' for name, value in hashes.items()) or '未记录'}",
        "",
        "## 总体指标",
        "",
        *table(["指标", "结果", "说明"], overall_rows(summaries)),
        "",
        "## 分题型结果",
        "",
        *table(["题型", "题数", "证据完整命中", "要点覆盖", "幻觉率"], group_rows(summaries)),
        "",
        "## 问题归因",
        "",
    ]

    counts = attribution_counts(summaries)
    if counts:
        lines += table(["环节", "备注数"], counts.most_common())
    else:
        lines.append("暂无。人工备注以“检索：”“重排：”“生成：”“工具：”开头后，这里会自动统计。")

    attention = [summary for summary in summaries if is_attention_case(summary)]
    lines += ["", f"## 需要复盘的题（{len(attention)} 题）", ""]
    if attention:
        lines += table(
            ["题号", "题型", "证据", "引用", "要点", "依据", "备注"],
            [(
                summary["case_id"], summary["group"],
                f"{summary['evidence_hits']}/{len(summary['evidence_rows'])}" if summary["evidence_rows"] else "不适用",
                score_text(summary["source_coverage"]) if summary["source_coverage"] is not None else "不适用",
                score_text(summary["human_coverage"]), score_text(summary["human_groundedness"]),
                "；".join(summary["comments"]) or "无",
            ) for summary in attention],
        )
    else:
        lines.append("没有未达标的题。")

    lines += [
        "",
        "## 指标口径",
        "",
        "- 人工分使用 travel-quality-v1 标准，分值为 0、0.5、1。",
        "- 要点覆盖：多轮题取各轮平均。依据分：多轮题取最低一轮，任何一轮编造都不能被其他轮抵消。",
        "- 幻觉率按题统计，未评分的题不进入分母，也不当作 0 分。",
        "- 证据完整命中不等于 Hit Rate@k 或 Recall@k；只统计有预期来源、且不需要反问的轮次。",
        "- 工具聊天没有结构化的反问标记，反问效果由人工要点覆盖判断：该反问的轮次没有反问，这一轮记 0 分。",
        "- 本报告与 historical-rag-round-* 的旧人工分口径不同，不能直接比较平均值。",
        "",
    ]
    return "\n".join(lines)


def latest_scores(scores):
    """同名分数可能改过多次，以最新一次为准。"""
    latest = {}
    for score in sorted(scores, key=lambda item: item.timestamp):
        latest[score.name] = {"value": score.value, "comment": score.comment}
    return latest


def read_langfuse_scores(client, trace_ids):
    """旧的 GET /traces 和 /v2/scores 已不可用，这里用 v3 分数接口和 v2 观测接口。"""
    data = {}
    for trace_id in trace_ids:
        scores = client.api.scores_v3.get_many_v3(trace_id=trace_id, fields=SCORE_FIELDS, limit=100).data
        item = latest_scores(scores)
        calls = client.api.observations.get_many(
            trace_id=trace_id, name="model-call", fields="core,usage", limit=100,
        ).data
        usage = [(call.usage_details or {}).get("total") for call in calls]
        item["tokens"] = sum(value for value in usage if value is not None) if usage else None
        data[trace_id] = item
    return data


def main():
    parser = argparse.ArgumentParser(description="汇总一次评测运行，生成 Markdown 报告")
    parser.add_argument("--run", type=Path, help="运行文件路径；默认使用最新结果")
    parser.add_argument("--out", type=Path, help="报告路径；默认保存在运行文件旁边")
    parser.add_argument("--offline", action="store_true", help="不读取 Langfuse，只用运行文件里的数据")
    parser.add_argument("--proxy", help="本次进程HTTP/HTTPS代理")
    args = parser.parse_args()

    if args.proxy:
        os.environ["HTTP_PROXY"] = args.proxy
        os.environ["HTTPS_PROXY"] = args.proxy

    run_path = args.run or find_latest_run()
    run = json.loads(run_path.read_text(encoding="utf-8"))

    langfuse_scores = {}
    if not args.offline:
        setup_tracing()
        try:
            client = get_tracing_client()
            if client is None:
                raise RuntimeError("请先设置 LANGFUSE_ENABLED=true，或使用 --offline")
            langfuse_scores = read_langfuse_scores(client, [case["trace_id"] for case in run["results"]])
        finally:
            shutdown_tracing()

    out_path = args.out or run_path.with_name(f"{run_path.stem}-report.md")
    out_path.write_text(build_report(run, langfuse_scores), encoding="utf-8")
    print("报告已生成：", out_path)


if __name__ == "__main__":
    main()
