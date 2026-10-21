import json
from time import perf_counter
from datetime import datetime
import os       #查找模型
from dotenv import load_dotenv   #读取evn文件
from pathlib import Path
from app.ingest import calculate_file_hash


def load_eval_cases(path):
    with open(path,"r",encoding="utf-8") as f:
        cases=json.load(f)

    return cases

#模拟超时
def fake_exception_caller(question, history, *, pending_question=None):
    return {
    "data": None,
    "error": ""
}
#假函数模拟
def fake_model_caller(question,history,*,pending_question=None):
    print(f"模拟通用，收到历史{len(history)}")

    return{
        "data":{
            "answer":"这里是模拟回答",
            "sources":[]
        },
        "error":"",
        "needs_clarification":False,
        "pending_question":None
    }
#假函数澄清模拟
def fake_clarification_caller(question,history,*,pending_question=None):
    print(f"历史条数：{len(history)},待补问题：{pending_question}")

    if pending_question is  None:
        return{
            "data": {
                "answer": "请补充商家及套餐名称",
                "sources": []
            },
            "error": "",
            "needs_clarification": True,
            "pending_question": question
        }
    return {
        "data": {
            "answer": "这是模拟最终回答",
            "sources": []
        },
        "error": "",
        "needs_clarification": False,
        "pending_question": None
    }

#真实调用函数
def real_model_caller(question, history, *, pending_question=None):
    from app.rag_resources import get_rag_resources
    from app.rag_pipeline import run_rag

    resources = get_rag_resources()

    return run_rag(
        question=question,
        history=history,
        model=resources["model"],
        collection=resources["collection"],
        reranker=resources["reranker"],
        pending_question=pending_question
    )


#单个问题调用
def run_rag_case(case,model_caller):
    history=[]  #【0，2】
    pending_question=None
    results=[]  
    failed=False


#内部循环更新历史和待处理的问题
    for turn_number,turn  in enumerate(case["turns"],start=1):
        question=turn["question"]

        item={  #每轮更新，继承到下一轮
            "case_id": case["id"],     #[E01]
            "turn_number": turn_number,    #[1]
            "question": question,   
            "status": "ok",
            "result": None,    #正常拿到的result
            "error": "",
            "elapsed_seconds":None,
            "expected": {
        "needs_clarification": turn["expected_needs_clarification"],  #是否需要
        "source_ids": turn["expected_source_ids"],   #【s02]
        "points": turn["expected_points"],     #期望做到的要点
        "forbidden_points": turn["forbidden_points"]    #不能做的要点
        },
        }

        if failed:
            item["status"]="skipped"
            item["error"]="前一轮失败，本轮还未调用"
            results.append(item)
            continue   #第一轮报错，不进行后续
        
        start=perf_counter() #计时开始


        try:
        
            result=model_caller(
                question,
                history=history,
                pending_question=pending_question
            )
            item["result"]=result

            if result["error"]:
                item["status"]="error"
                item["error"]=result["error"]  #程序所有可能报错的地方
            elif result["data"] is None:
                item["status"]="error"
                item["error"]="没有返回答案"
            else:
                answer=result["data"]["answer"]

                history.append({
                    "role":"user",
                    "content":question
                })
                history.append({
                    "role":"assistant",
                    "content":answer
                })

                pending_question=result["pending_question"]  #运行之后从result拿到的question
        except Exception as error:
            item["status"]="error"
            item["error"]=f"{type(error).__name__}:{error}"  #程序自动报错，去它错误名

        item["elapsed_seconds"]=round(perf_counter() - start,4)  #round(..., 4) 表示保留四位小数

        if item["status"]=="error":    
            failed=True   #是否失败，是
        results.append(item)
    return results

#引入哈希，自动记录本次使用的代码、题目和资料版本
def collect_version_hashes():
    paths = list(Path("app").glob("*.py"))   
    paths.extend(Path("data/raw").glob("*.md"))  #资料
    paths.append(Path("examples/rag_eval_cases.json"))   #题目
    paths.append(Path("examples/run_rag_eval.py"))    #代码

    hashes = {}

    for path in sorted(paths):
        hashes[str(path)] = calculate_file_hash(path)

    return hashes


#保存路线
def save_eval_results(results,path):
    with open(path,"w",encoding="utf-8") as f:
        json.dump(results,f,ensure_ascii=False,indent=2)

def main():
    output_path = (
        "examples/rag_eval_results_"
        + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        + ".json"
    )
    cases=load_eval_cases("examples/rag_eval_cases.json")

    print(f"题目数量:{len(cases)}")


    load_dotenv()

    selected_case_ids = []
    for case in cases:
        selected_case_ids.append(case["id"])

    run_info = {
    "started_at": datetime.now().astimezone().isoformat(),    #记录开始时间，包含电脑本地时区。
    "mode": "real",    #明确标记为模拟运行。
    "caller": "real_model_caller",     #本次实际使用的函数名称，目前手动填写
    "model": os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),       #调用真实模型
    "selected_case_ids": selected_case_ids,             #本次选了哪些题。
    "collection": "travel_documents_full_20161014_v2",   #向量集合
    "chunk_size": 400,          #尺寸
    "chunk_overlap": 80,         #每片保留
    "retrieval_n_results_per_query": 7,      #与当前检索调用保持一致
    "rerank_top_k_per_query": 3,        #与当前重排调用保持一致
    "version_hashes": collect_version_hashes(),     #哈希
}
    all_results=[]
    report = {
            "run_info": run_info,
            "results": all_results
        }
    for case in cases:

        if case["id"] in run_info["selected_case_ids"]:
            results=run_rag_case(case,real_model_caller)  #替换假model运行。
            all_results.extend(results)

            save_eval_results(
                    report,
                    output_path
                )

            for item in results:
                print(
                    item["case_id"],
                    item["turn_number"],
                    item["status"],
                    item["error"]
                )
    
if __name__ == "__main__":
    main()
