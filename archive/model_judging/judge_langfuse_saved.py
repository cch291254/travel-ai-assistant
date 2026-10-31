"""复用云端已有回答进行业务质量评分。默认E03，不重跑助手，结果缓存可复用。"""
import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter

from app.eval_judge import (
    RUBRIC_VERSION, CaseJudgment, build_judge_input, call_judge,
    judge_fingerprint, quality_scores,
)
from app.tracing import setup_tracing, get_tracing_client, shutdown_tracing

ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = ROOT / "examples" / "quality_reviews"


def sync_scores(client, row, scores, *, source, model, fingerprint, rubric_version):
    for score in scores:
        # 同一原记录、评分来源和标准复用ID，重复同步不会叠加一份分数。
        score_id = hashlib.sha256(f"{row.trace_id}:{row.id}:{source}:{score['name']}".encode()).hexdigest()[:32]
        client.create_score(
            trace_id=row.trace_id, observation_id=row.id, score_id=score_id,
            name=score["name"], value=score["value"], data_type="NUMERIC",
            comment=score["comment"], metadata={"scoring_source": source,
                "judge_model": model, "rubric_version": rubric_version, "fingerprint": fingerprint},
        )
    client.flush()


def review_saved(client, row, human_review_path=None):
    material = build_judge_input(row.output, row.expected_output)
    model = os.getenv("EVAL_JUDGE_MODEL") or os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
    fingerprint = judge_fingerprint(material, model)
    RESULT_DIR.mkdir(exist_ok=True)
    path = RESULT_DIR / f"{row.trace_id}-{fingerprint[:12]}.json"

    if human_review_path:
        review = json.loads(Path(human_review_path).read_text(encoding="utf-8"))
        if review["source_trace_id"] != row.trace_id or review["source_observation_id"] != row.id:
            raise ValueError("人工复核文件与所选原记录不一致，停止同步")
        fields = ("answer_coverage", "groundedness")
        if any(review[field] not in (0, 0.5, 1) for field in fields) or not review["reason"].strip():
            raise ValueError("人工分数只能为0、0.5、1，且必须填写理由")
        scores = [{"name": "human_" + field, "value": review[field], "comment": review["reason"]} for field in fields]
        sync_scores(client, row, scores, source="human", model="", fingerprint=fingerprint, rubric_version=RUBRIC_VERSION)
        print("人工复核已同步；模型初评分保留，人工评分使用human_前缀。")
        return

    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))
        judgment = CaseJudgment.model_validate(saved["judgment"])
        print("复用本地评分缓存，没有新增模型请求。")
    else:
        started = perf_counter()
        with client.start_as_current_observation(
            as_type="generation", name="quality-judge", model=model,
            input={"case_id": row.metadata.get("case_id"), "turn_count": len(material["turns"])},
            metadata={"source_trace_id": row.trace_id, "rubric_version": RUBRIC_VERSION},
        ) as generation:
            judgment, usage = call_judge(material, model)
            generation.update(output=judgment.model_dump(), usage_details={
                "input": usage.get("prompt_tokens", 0), "output": usage.get("completion_tokens", 0),
                "total": usage.get("total_tokens", 0),
            })
        saved = {"source_trace_id": row.trace_id, "source_observation_id": row.id,
                 "experiment": row.experiment_name, "case_id": row.metadata.get("case_id"),
                 "judge_model": model, "rubric_version": RUBRIC_VERSION,
                 "fingerprint": fingerprint, "judge_elapsed_seconds": perf_counter() - started,
                 "judge_usage": usage, "material": material, "judgment": judgment.model_dump(),
                 "status": "模型初评，待人工抽查"}
        path.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
    scores = quality_scores(judgment)
    sync_scores(client, row, scores, source="model", model=model, fingerprint=fingerprint, rubric_version=RUBRIC_VERSION)

    print("\n实验：", row.experiment_name)
    for original, grade in zip(material["turns"], judgment.turns):
        print(f"\n第 {grade.turn_number} 轮问题：{original['question']}")
        print("实际回答：", original["answer"])
        print(f"要点覆盖：{grade.answer_coverage}；{grade.coverage_reason}")
        print(f"事实与边界：{grade.groundedness}；{grade.groundedness_reason}")
        print("评分模型建议复核：", grade.needs_review)
    print("\n案例平均分：", {score["name"]: score["value"] for score in scores})
    print("中文明细已保存：", path)
    review_path = path.with_name(path.stem + "-human.json")
    if not review_path.exists():
        review_path.write_text(json.dumps({
            "source_trace_id": row.trace_id, "source_observation_id": row.id,
            "answer_coverage": None, "groundedness": None, "reason": "",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("需纠正时填写人工复核文件，再用 --human-review 同步：", review_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", help="指定已有实验全名；默认选择最新tool-agent-E03实验")
    parser.add_argument("--case", default="E03")
    parser.add_argument("--human-review", help="同步已填写的人工分数，不调用评分模型")
    parser.add_argument("--proxy", help="为本次进程设置HTTP/HTTPS代理")
    args = parser.parse_args()
    if not args.human_review:
        parser.error("模型自动评分已停用；本脚本仅保留 --human-review 人工分数同步入口")
    if args.proxy:
        os.environ["HTTP_PROXY"] = args.proxy
        os.environ["HTTPS_PROXY"] = args.proxy
    setup_tracing()
    try:
        client = get_tracing_client()
        if client is None:
            raise RuntimeError("请开启LANGFUSE_ENABLED")
        query = dict(from_start_time=datetime.now(timezone.utc) - timedelta(days=30),
                     fields="core,io,metadata", limit=100)
        if args.experiment:
            query["experiment_name"] = args.experiment
        response = client.api.experiments.list_items(**query)
        matches = [row for row in response.data if (row.metadata or {}).get("case_id") == args.case
                   and (args.experiment or row.experiment_name.startswith("tool-agent-E03"))]
        if not matches:
            raise ValueError("未找到所选实验的案例记录；请用--experiment指定完整实验名")
        row = max(matches, key=lambda item: item.start_time)
        review_saved(client, row, args.human_review)
    finally:
        shutdown_tracing()


if __name__ == "__main__":
    main()
