from app.vector_store import query_chunks
from app.reranker import rerank_chunks
from app.device import MODEL_DEVICE

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
    model.to(MODEL_DEVICE)

    results=query_chunks(
        question,
        model,
        collection,
        n_results=n_results,#召回的top_k
        where=where,
    )
    
    model.to("cpu")

    if not results["documents"][0]:
        return[]

    reranker.to(MODEL_DEVICE)

    return rerank_chunks(
        question,
        results,
        reranker,
        top_k=top_k
    )
