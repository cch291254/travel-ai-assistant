from app.tool_calling import run_tool_chat
import argparse
import hashlib
import subprocess
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from app.tracing import (
    setup_tracing,
    get_tracing_client,
    shutdown_tracing,
)

#运行成功                        #接受其他带名字的参数
def run_eval_case(*,item,**kwargs):
    history=[]
    results=[]

    #按顺序取题
    for turn_number,question in enumerate(item.input["questions"],start=1):
        #调用当前工具聊天流程
        started = perf_counter()
        result=run_tool_chat(question,history=history)

        #保存本轮问题
        results.append({
            "turn_number":turn_number,
            "question":question,
            "result":result,
            "elapsed_seconds": perf_counter() - started,
        })

        if result["error"]:
            break

        # 评测不经过 /chat，模型要求保存草案时，在这里用同样的对话生成，供人工核对
        if result.get("draft_requested"):
            from app.draft_generator import generate_draft

            draft_result=generate_draft(history+[
                {"role":"user","content":question},
                {"role":"assistant","content":result["answer"]},
            ],None)
            results[-1]["draft"]=draft_result["draft"]
            results[-1]["draft_error"]=draft_result["error"]

        history.append({
            "role": "user",
            "content": question,
        })
        history.append({
            "role":"assistant",
            "content":result["answer"],
        })

    return {"turns":results}

#检查执行完成
def evaluate_execution(*,input,output,**kwargs):
    #input是输入问题，output是run_eval返回值
    turns=output["turns"]

    if len(turns)!=len(input["questions"]):
        return{
            "name":"execution_complete",
            "value":0,
            "comment":"未完全全部对话"
        }

    for turn in turns:
        if turn["result"]["error"]:
            return{
                "name": "execution_complete",  #名称
                "value": 0,    #得分表示完整
                "comment": "某轮返回了错误",
            }


    return {
        "name":"execution_complete",
        "value":1,
        "comment":"全部执行完成，且未返回错误"
    }


def get_cited_source_ids(result):
    #自动去重
    source_ids=set()


    for catation in result.get("citations",[]):
        source_id=catation["metadata"].get("source_id")


        if source_id:
            source_ids.add(source_id)

    return source_ids

#检查来源覆盖是否完整
def evaluate_source_coverage(*,output,expected_output,**kwargs):
    matched=0  #实际匹配到的预期数量
    required=0  #预期的
    turns=output["turns"]


    #按顺序检查每轮的预期来源。
    for index,expected_turn in enumerate(expected_output["turns"]):
        expected_ids=set(expected_turn["source_ids"])   #过滤
        required+=len(expected_ids)    #预期所以id数量

        if index>=len(turns):
            continue

        actual_ids=get_cited_source_ids(turns[index]["result"])

        #趣交集：同时出现在预期和实际来源
        matched+=len(expected_ids&actual_ids)

    #没有要求引用来源的题目，不评分
    if required==0:
        return []

    return {
        "name": "source_coverage",
        "value": matched / required,   #两种评分
        "comment": f"匹配到 {matched}/{required} 个预期来源",
    }


def get_evidence_source_ids(result):
    source_ids=set()

    for item in result.get("evidence",[]):
        source_id=item["metadata"].get("source_id")

        if source_id:
            source_ids.add(source_id)

    return source_ids


#检查预期来源是否进入最终证据；和引用覆盖分开，才能区分检索问题和回答问题
def evaluate_evidence_coverage(*,output,expected_output,**kwargs):
    matched=0
    required=0
    turns=output["turns"]

    for index,expected_turn in enumerate(expected_output["turns"]):
        #应该反问的轮次不需要检索
        if expected_turn["needs_clarification"]:
            continue

        expected_ids=set(expected_turn["source_ids"])
        required+=len(expected_ids)

        if index>=len(turns):
            continue

        actual_ids=get_evidence_source_ids(turns[index]["result"])
        matched+=len(expected_ids&actual_ids)

    if required==0:
        return []

    return {
        "name": "evidence_coverage",
        "value": matched / required,
        "comment": f"证据中找到 {matched}/{required} 个预期来源",
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="默认只跑E03；--all跑完整题集；仅执行完成和来源覆盖两个规则检查")
    parser.add_argument("--all", action="store_true", help="运行完整题集，会产生助手用量")
    parser.add_argument("--case", nargs="+", default=["E03"], help="运行指定题号，可写多个，例如 --case E01 E03 E07")
    parser.add_argument("--proxy", help="本次进程HTTP/HTTPS代理")
    parser.add_argument("--dataset", default="travel-rag-v1", help="Langfuse 题集名，留出集是 travel-rag-holdout-v1")
    args = parser.parse_args()
    if args.proxy:
        os.environ["HTTP_PROXY"] = args.proxy
        os.environ["HTTPS_PROXY"] = args.proxy
    # 初始化追踪，读取本地 Langfuse 配置。
    setup_tracing()
    client = get_tracing_client()

    if client is None:
        raise RuntimeError("请先设置 LANGFUSE_ENABLED=true")

    try:
        # 从云端读取已经上传的题集。
        dataset = client.get_dataset(args.dataset)

        # 每道题独立执行；同一道题内按顺序保留多轮历史。
        # 只取题库上传的题目：编号固定，页面从运行记录加入的条目不是标准题。
        selected_items = [
            item
            for item in dataset.items
            if item.id.startswith(f"{args.dataset}-")
            and (args.all or item.metadata["case_id"] in args.case)
        ]

        if not selected_items:
            raise ValueError("未找到指定题号，或完整题集为空")
        if not args.all and {item.metadata["case_id"] for item in selected_items} != set(args.case):
            raise ValueError("部分指定题号不存在，请检查 --case")
        selected_items.sort(key=lambda item: item.metadata["case_id"])
        evaluators = [evaluate_execution, evaluate_source_coverage,evaluate_evidence_coverage]
        git_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[1],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        root = Path(__file__).resolve().parents[1]
        hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in (
            "app/tool_calling.py", "app/tools.py", "examples/rag_eval_cases.json", "examples/rag_eval_holdout.json")}
        run_prefix = "tool-agent" if args.dataset == "travel-rag-v1" else args.dataset

        # 执行选定题目，并记录追踪。
        experiment = client.run_experiment(
            name=f"{run_prefix}-full" if args.all else f"{run_prefix}-" + "-".join(sorted(set(args.case))),
            data=selected_items,
            task=run_eval_case,
            evaluators=evaluators,
            max_concurrency=1,
            metadata={**{"sha_" + Path(name).stem: value for name, value in hashes.items()},
                      "assistant_model": os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
                      "judge_enabled": "False",
                      "judge_model": "disabled",
                      "git_commit": git_commit},
        )

        # 每次完整保存问答、标准、分数和追踪编号，后续无需手工抄写。
        output_dir = root / "examples" / "evaluation_runs"
        output_dir.mkdir(exist_ok=True)
        result_path = output_dir / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S%f}.json"
        result_path.write_text(json.dumps({
            "run_name": experiment.run_name, "code_hashes": hashes,"git_commit":git_commit,
            "requested_cases": [item.metadata["case_id"] for item in selected_items],
            "judge_enabled": False,
            "dataset": args.dataset,
            "results": [{"case_id": row.item.metadata["case_id"], "trace_id": row.trace_id,
                         "group": row.item.metadata.get("group"),
                         "paraphrase_of": row.item.metadata.get("paraphrase_of"),
                         "input": row.item.input, "expected_output": row.item.expected_output,
                         "output": row.output,
                         "scores": [{"name": score.name, "value": score.value, "reason": score.comment}
                                    for score in row.evaluations]} for row in experiment.item_results],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print("完整中文结果已保存：", result_path)
        if len(experiment.item_results) != len(selected_items):
            print("注意：部分案例执行失败，记录数量不足，请查看日志；不能按完整评测统计。")
        if any(not row.evaluations for row in experiment.item_results):
            print("注意：部分评分失败，不能把缺失评分当作0分或满分。")

        print(experiment.format())
        print("查看结果：", experiment.dataset_run_url)

    finally:
        # 发送剩余追踪记录，关闭客户端。
        shutdown_tracing()
