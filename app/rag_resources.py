from functools import lru_cache

#rag数据源
@lru_cache(maxsize=1)   #当前 Python 进程中，最多缓存一组调用结果
def get_rag_resources(collection_name="travel_documents_full_20161014_v2",):
    from app.embedding import load_embedding_model
    from app.vector_store import get_vector_collection
    from app.reranker import load_reranker

    collection = get_vector_collection(collection_name)

    model=load_embedding_model()
    model.to("cpu")

    reranker=load_reranker()

    return {
        "model":model,
        "collection":collection,
        "reranker":reranker
    }