from app.vector_store import query_chunks
from app.reranker import rerank_chunks

#整合召回和冲排序
def retrieve_evidence(
        question,
        model,
        collection,
        reranker,
        where=None,
        n_results=7,
        top_k=3,
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
    # print("\n实际检索问题：", question)
    # print("来源过滤：", where)

    # for rank, (chunk_id, metadata) in enumerate(
    #     zip(results["ids"][0], results["metadatas"][0]),
    #     start=1,
    # ):
    #     print("初召回：", rank, chunk_id,
    #         "来源：", metadata.get("source_id"))

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
