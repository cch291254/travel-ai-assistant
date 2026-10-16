from app.embedding import load_embedding_model
from app.vector_store import get_vector_collection
from app.reranker import load_reranker
from pprint import pprint
from app.retrieval import retrieve_evidence
from app.rag_context import build_context
from app.rag_answer import generate_rag_answer

collection = get_vector_collection(name="travel_documents_bge_m3_titles_v4")


question=input("请输入问题：").strip()

if question:
    model = load_embedding_model()
    model.to("cpu")
    reranker = load_reranker()
    evidence = retrieve_evidence(
    question,
    model,
    collection,
    reranker,
    where={
        "source_title": "S05 套餐2：私家团包团一日游行程"
    },
    n_results=5,
    top_k=2,
)

    context_result = build_context(evidence)

    answer_result = generate_rag_answer(question, context_result)
    pprint(answer_result)

else:
    print("问题不能为空")
