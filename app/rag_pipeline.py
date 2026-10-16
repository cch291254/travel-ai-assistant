from app.query_rewriter import rewrite_retrieval_question
from app.retrieval import retrieve_evidence
from app.rag_context import build_context
from app. rag_answer import generate_rag_answer


def run_rag(
        question,
        history,
        model,
        collection,
        reranker,
        pending_question=None,
):

    result={
        "data":None,
        "citations":[],
        "evidence":[],
        "rewrite_record":None,
        "record":None,
        "error":"",
        "needs_clarification":False,
        "pending_question":pending_question
    }

    rewrite_input=question
    if pending_question is not None:
        rewrite_input=(
            pending_question
            +"\n用户补充信息："
            +question
        )

    rewrite_result=rewrite_retrieval_question(
            rewrite_input,
            history,
        )

    result["rewrite_record"]=rewrite_result["record"]

    if rewrite_result["error"]:
        result["error"]=rewrite_result["error"]
        return result 
        #再次判断需不需要澄清
    if rewrite_result["needs_clarification"]:
        result["needs_clarification"]=True
        result["pending_question"]=rewrite_input
        result["data"]={
            "answer":rewrite_result["clarification_question"],
            "sources":[]
        }
        return result


    result["pending_question"]=None

    #检索、合并证据和回答
    retrieval_question = rewrite_result["answer"].strip()

    target_source_ids = rewrite_result["target_source_ids"]
    where = None
    if target_source_ids:
            where = {
                "source_id": {"$in": target_source_ids}
            }

    #子问题检索后，如果重复就去掉
    sub_questions = rewrite_result["sub_questions"]
    evidence = []
    seen_chunk_ids = set()

    for query_index, sub_question in enumerate(sub_questions, start=1):
        branch_evidence = retrieve_evidence(
            sub_question,
            model,
            collection,
            reranker,
            where=where,
            n_results=5,
            top_k=2
        )

        for item in branch_evidence:
            if item["chunk_id"] not in seen_chunk_ids:
                seen_chunk_ids.add(item["chunk_id"])
                evidence.append(item)

    result["evidence"]=evidence
    context_result = build_context(evidence)
    
    answer_result=generate_rag_answer(question,context_result,retrieval_question=retrieval_question)
    result["record"]=answer_result["record"]
    if answer_result["error"]:
        result["error"]=answer_result["error"]
        return  result

    if answer_result["data"] is None:
        result["error"]="回答阶段未返回有效数据"
        return result
    result["data"]=answer_result["data"]
    result["citations"]=answer_result["citations"]

    return result