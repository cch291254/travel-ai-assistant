import json
from pathlib import Path
from dotenv import load_dotenv
from langfuse import get_client


#定位项目中的原始题集
root=Path(__file__).resolve().parents[1]
case_path=root/"examples"/"rag_eval_cases.json"

#json文件转化pathon列表
cases=json.loads(case_path.read_text(encoding="utf-8"))

items=[]

for case in cases:
    item={
        #输入：按顺序保留这道题的全部提问
        "input":{
            "questions":[
                turn["question"]for turn in case["turns"]
            ]
        },
        "expected_output": {
            "turns": [
                {
                    "needs_clarification": turn["expected_needs_clarification"],
                    "source_ids": turn["expected_source_ids"],
                    "points": turn["expected_points"],
                    "forbidden_points": turn["forbidden_points"],
                }
                for turn in case["turns"]
            ]
        },

        # 元数据：方便对应原来的 E01、E02 等题号。
        "metadata": {
            "case_id": case["id"],
            "turn_count": len(case["turns"]),
        },
    }
    items.append(item)




# 读取本地连接配置，创建 Langfuse 客户端。
load_dotenv(root / ".env")
client = get_client()

dataset_name = "travel-rag-v1"

try:
    # 在当前 Langfuse 项目下创建评测题集。
    client.create_dataset(
        name=dataset_name,
        description="旅行助手评测题集，包含单轮和多轮案例",
        metadata={"source_file": case_path.name},
    )

    # 先上传前三道题，验证结构。
    for item in items:
        case_id = item["metadata"]["case_id"]

        client.create_dataset_item(
            dataset_name=dataset_name,

            # 固定编号：重复运行时更新同一题，避免重复添加。
            id=f"{dataset_name}-{case_id}",

            input=item["input"],
            expected_output=item["expected_output"],
            metadata=item["metadata"],
        )

        print("已上传：", case_id)

finally:
    # 关闭客户端，释放资源。
    client.shutdown()