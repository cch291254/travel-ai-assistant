"""导入三轮历史评测；默认仅生成本地预览，--upload 才上传，不调用模型。"""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "examples" / "langfuse_history"
HISTORY_DIR = ROOT / "docs" / "evaluation" / "history"
DATASET_NAME = "travel-rag-v1"
ROUNDS = {
    1: ("round1_results.json", "round1_review.md", 27, 29, 15),
    2: ("round2_results.json", "round2_review.md", 30, 40, 13),
    3: ("round3_results.json", "round3_review.md", 30, 40, 22),
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review_sections(text):
    """保留原人工评审；仅规范化 E019 这样的题号，不改原文。"""
    pattern = r"^##\s+(E\d+)\b[^\n]*\n(.*?)(?=^##\s+E\d+\b|\Z)"
    sections = {}
    for match in re.finditer(pattern, text, re.M | re.S):
        case_id = f"E{int(match[1][1:]):02d}"
        if case_id in sections:
            raise ValueError(f"人工评审存在重复题号：{case_id}")
        sections[case_id] = {"original_heading": match[1], "text": match[2].strip()}
    return sections


def prepare_round(number):
    result_name, review_name, case_count, turn_count, pass_count = ROUNDS[number]
    result_path = HISTORY_DIR / result_name
    review_path = HISTORY_DIR / review_name
    history = json.loads(result_path.read_text(encoding="utf-8"))
    review_text = review_path.read_text(encoding="utf-8")
    sections = review_sections(review_text)
    grouped = {}
    for row in history["results"]:
        grouped.setdefault(row["case_id"], []).append(row)

    cases = []
    for case_id, rows in sorted(grouped.items()):
        rows = sorted(rows, key=lambda row: row["turn_number"])
        if [row["turn_number"] for row in rows] != list(range(1, len(rows) + 1)):
            raise ValueError(f"{case_id} 轮次重复或有缺口，需要人工核对")
        review = sections[case_id]
        labels = re.findall(
            r"^[^\S\n]*-[^\S\n]*答案正确性[^\S\n]*[:：][^\S\n]*([^\n]*)",
            review["text"], re.M,
        )[:len(rows)]
        # 沿用旧报告口径：部分通过、未完成、未评估均不计为准确。
        # 第一轮 E07 只实际测试首问，后续未验证说明保留在原评审中。
        answer_correct = int(
            len(labels) == len(rows)
            and all(re.match(r"^通过(?:$|[，,。；;])", label) for label in labels)
        )
        output_turns = []
        for row in rows:
            result = row.get("result") or {}
            citations = result.get("citations") or []
            cited_chunks = {citation["chunk_id"] for citation in citations}
            output_turns.append({
                "turn_number": row["turn_number"],
                "question": row["question"],
                "status": row["status"],
                "answer": (result.get("data") or {}).get("answer"),
                "error": row.get("error") or result.get("error"),
                "needs_clarification": result.get("needs_clarification"),
                "citations": citations,
                "cited_evidence": [
                    evidence for evidence in (result.get("evidence") or [])
                    if evidence["chunk_id"] in cited_chunks
                ],
                "historical_elapsed_seconds": row.get("elapsed_seconds"),
                "historical_answer_record": result.get("record"),
                "historical_rewrite_record": result.get("rewrite_record"),
            })
        cases.append({
            "case_id": case_id,
            "input": {"questions": [row["question"] for row in rows]},
            "expected_output": {"turns": [row["expected"] for row in rows]},
            "output": {"turns": output_turns, "original_human_review": review["text"]},
            "original_review_heading": review["original_heading"],
            "answer_labels": labels,
            "legacy_answer_correct": answer_correct,
            "legacy_execution_ok": int(all(row["status"] == "ok" for row in rows)),
            # 完整原记录保存在本地，云端展示实际回答、引用和原指标。
            "original_rows": rows,
        })

    if (len(cases), len(history["results"]), sum(c["legacy_answer_correct"] for c in cases)) != (
        case_count, turn_count, pass_count
    ):
        raise ValueError(f"第 {number} 轮的数量或人工评分汇总与原报告不一致，停止导入")
    fingerprint = hashlib.sha256(
        (sha256(result_path) + sha256(review_path) + "history-v1").encode()
    ).hexdigest()
    return {
        "round": number,
        "experiment_name": f"historical-rag-round-{number}-{fingerprint[:12]}",
        "source_file": result_name,
        "source_sha256": sha256(result_path),
        "review_file": review_name,
        "review_sha256": sha256(review_path),
        "original_run_info": history["run_info"],
        "original_review_preamble": re.split(r"^##\s+E\d+\b", review_text, maxsplit=1, flags=re.M)[0],
        "cases": cases,
    }


def upload_round(client, prepared, selected_ids):
    """导入动作创建新记录；不伪造当时的 generation、时间线或延迟。"""
    dataset = client.get_dataset(DATASET_NAME)
    cloud_items = {item.metadata["case_id"]: item for item in dataset.items}
    experiment_name = prepared["experiment_name"]
    existing = client.api.experiments.list_items(
        from_start_time=datetime(2026, 10, 1, tzinfo=timezone.utc),
        experiment_name=experiment_name, fields="core,dataset", limit=100,
    )
    existing_ids = {item.experiment_item_id for item in existing.data}
    by_id = {case["case_id"]: case for case in prepared["cases"]}
    items = []
    for case in prepared["cases"]:
        case_id = case["case_id"]
        if selected_ids and case_id not in selected_ids:
            continue
        cloud = cloud_items[case_id]
        if cloud.id in existing_ids:
            continue
        # 关联同一题号用于比较；传入旧题目和旧标准的快照，不覆盖云端题集。
        # 旧版少测的追问不会被补生成，也不会借用新版标准重评。
        questions = cloud.input["questions"]
        if questions[:len(case["input"]["questions"])] != case["input"]["questions"]:
            raise ValueError(f"{case_id} 的云端题目与历史题目不同，需要人工核对")
        items.append(cloud.model_copy(update={
            "input": case["input"],
            "expected_output": case["expected_output"],
            "metadata": {**cloud.metadata, "case_id": case_id,
                         "turn_count": len(case["original_rows"]), "historical_import": True},
        }))

    if not items:
        print(f"第 {prepared['round']} 轮：所选记录已存在，跳过上传")
        return

    def historical_task(*, item, **kwargs):
        # 完整配置放在单条记录详情中，避免实验摘要的200字符元数据限制。
        client.update_current_span(metadata={
            "original_run_info": prepared["original_run_info"],
            "original_review_preamble": prepared["original_review_preamble"],
        })
        return by_id[item.metadata["case_id"]]["output"]

    def historical_scores(*, metadata, **kwargs):
        case = by_id[metadata["case_id"]]
        return [
            {"name": "legacy_answer_correct", "value": case["legacy_answer_correct"],
             "comment": "沿用原人工评审，部分通过计0；" + " / ".join(case["answer_labels"])},
            {"name": "legacy_execution_ok", "value": case["legacy_execution_ok"],
             "comment": "原结果中已记录的各轮是否全部为ok；不代表业务答案正确"},
        ]

    experiment = client.run_experiment(
        name=experiment_name, run_name=experiment_name,
        description="历史结果导入；页面延迟为导入耗时，非原模型延迟。旧人工评分保持原口径。",
        data=items, task=historical_task, evaluators=[historical_scores], max_concurrency=3,
        metadata={
            "historical_import": "true", "source_file": prepared["source_file"],
            "source_sha256": prepared["source_sha256"],
            "original_started_at": prepared["original_run_info"]["started_at"],
            "review_file": prepared["review_file"], "review_sha256": prepared["review_sha256"],
            "timing_note": "Import spans measure import only. Historical timings/usage are in output.",
            "dataset_note": "Dataset link is case identity; task input/expected_output are historical snapshots.",
        },
    )
    client.flush()
    receipt = {
        "experiment": experiment_name, "experiment_id": experiment.experiment_id,
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "source_sha256": prepared["source_sha256"],
        "items": [{"case_id": item.item.metadata["case_id"], "trace_id": item.trace_id,
                   "evaluation_count": len(item.evaluations), "dataset_run_id": item.dataset_run_id}
                  for item in experiment.item_results],
    }
    receipt_path = OUTPUT_DIR / f"round-{prepared['round']}-receipt-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%f}.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    incomplete = len(experiment.item_results) != len(items) or any(
        len(item.evaluations) != 2 or not item.dataset_run_id for item in experiment.item_results
    )
    print(f"第 {prepared['round']} 轮：提交 {len(items)} 个历史案例，返回 {len(experiment.item_results)} 个")
    if incomplete:
        raise RuntimeError(f"部分导入失败，详情见 {receipt_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upload", action="store_true", help="上传已有历史结果，不调用模型")
    parser.add_argument("--round", type=int, choices=ROUNDS, nargs="+", default=list(ROUNDS))
    parser.add_argument("--case", nargs="+", help="仅导入指定案例，例如 E03，用于小量验证")
    parser.add_argument("--proxy", help="仅为本次进程设置 HTTP/HTTPS 代理")
    args = parser.parse_args()
    prepared_rounds = [prepare_round(number) for number in args.round]
    OUTPUT_DIR.mkdir(exist_ok=True)
    for prepared in prepared_rounds:
        path = OUTPUT_DIR / f"round-{prepared['round']}-prepared.json"
        path.write_text(json.dumps(prepared, ensure_ascii=False, indent=2), encoding="utf-8")
        count = len(prepared["cases"])
        turns = sum(len(case["original_rows"]) for case in prepared["cases"])
        correct = sum(case["legacy_answer_correct"] for case in prepared["cases"])
        print(f"第 {prepared['round']} 轮：{count} 案例 / {turns} 轮，原人工准确 {correct}/{count} ({correct/count:.2%})")
    if not args.upload:
        print("本地预览已生成；未连接云端，未调用模型。")
        return
    if args.proxy:
        import os
        os.environ["HTTP_PROXY"] = args.proxy
        os.environ["HTTPS_PROXY"] = args.proxy
    from app.tracing import setup_tracing, get_tracing_client, shutdown_tracing
    setup_tracing()
    try:
        client = get_tracing_client()
        if client is None:
            raise RuntimeError("请在本地配置 LANGFUSE_ENABLED=true")
        for prepared in prepared_rounds:
            upload_round(client, prepared, set(args.case or []))
    finally:
        shutdown_tracing()


if __name__ == "__main__":
    main()
