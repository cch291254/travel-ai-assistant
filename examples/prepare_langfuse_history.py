import json
from pathlib import Path

#定位结果
root=Path(__file__).resolve().parents[1]
history_path=root/"docs"/"evaluation"/"history"/"round3_results.json"

history=json.loads(history_path.read_text(encoding="utf-8"))

#按当前题号收集结果
grouped={}

for row in history["results"]:
    case_id=row["case_id"]

    #第一次遇到这个题号
    if case_id not in grouped:
        grouped[case_id]=[]

    grouped[case_id].append(row)

#题目单独的云端编号
cases=[]

for case_id,turns in grouped.items():
    cases.append({
        "case_id":case_id,
        "dataset_item_id":f"travel-rag-v1-{case_id}",   #新编号
        "turns":sorted(
            turns,    
            key=lambda turn:turn["turn_number"]  #第几轮
        )
    })

#历史运行配置
prepared={
    "source_file":history_path.name,
    "run_info":history["run_info"],
    "cases":cases
}

#写入新文件，不覆盖
output_path=root/"examples"/"langfuse_history_prepared.json"
output_path.write_text(
    json.dumps(prepared,ensure_ascii=False,indent=2),  #写入历史运行配置
    encoding="utf-8"
)

print("案例数量：", len(cases))
print("总轮数：", sum(len(case["turns"]) for case in cases))
print("已保存：", output_path)