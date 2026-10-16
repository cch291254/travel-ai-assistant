from app.vector_store import query_chunks
from app.reranker import rerank_chunks

#整合召回和冲排序
def retrieve_evidence(
        question,
        model,
        collection,
        reranker,
        where=None,
        n_results=5,
        top_k=2,
):

    reranker.to("cpu")
    model.to("cuda")

    results=query_chunks(
        question,
        model,
        collection,
        n_results=n_results,#召回的top_k
        where=where,
    )
    #查询召回片段
    # for rank, (chunk_id, content) in enumerate(
    # zip(results["ids"][0], results["documents"][0]),
    # start=1,
    # ):
    #     print("召回候选：", rank, chunk_id)
    #     print(content)

    model.to("cpu")

    if not results["documents"][0]:
        return[]

    reranker.to("cuda")

    return rerank_chunks(
        question,
        results,
        reranker,
        top_k=top_k
    )