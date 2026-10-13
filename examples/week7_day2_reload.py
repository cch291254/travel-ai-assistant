from pprint import pprint
from app.embedding import load_embedding_model
from app.vector_store import get_vector_collection, query_chunks
from sentence_transformers import CrossEncoder

collection = get_vector_collection(name="travel_documents_bge_m3_titles_v4")
print("当前集合：", collection.name)
print("集合记录数：", collection.count())

model=load_embedding_model()
model.max_seq_length=512
model.half()

question=input("请输入问题：").strip()

if question:
    results = query_chunks(
    question,
    model,
    collection,
    n_results=5,
    where=None
)
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]
    ids = results["ids"][0]
    rerank_texts=[]

    for index, document in enumerate(documents):
        section_path=metadatas[index].get("section_path","")
        text=section_path+"\n"+document
        rerank_texts.append(text)

#重排序
    model.to("cpu")

    reranker=CrossEncoder(
        "BAAI/bge-reranker-v2-m3",
        device="cuda",
        local_files_only=True,
    )
    reranker.max_seq_length=512
    reranker.half()

    ranked=reranker.rank(
        question,
        rerank_texts,
        top_k=len(rerank_texts),
        batch_size=2
    )

    print("重排后的全部候选ID：",
      [ids[item["corpus_id"]] for item in ranked])
#设立去重
    selected=[]
    seen_paragraphs=set()
    for rank in ranked:
        index=rank["corpus_id"]
        metadata=metadatas[index]

        paragraph_key=(
            metadata.get("document_id"),
            metadata.get("paragraph_index"),
        )

        if paragraph_key in seen_paragraphs:
            continue

        seen_paragraphs.add(paragraph_key)
        selected.append(rank)
        if len(selected)==2:
            break

    print("重排序筛选后的结果:")


    for rank,item in enumerate(selected,start=1):
        index=item["corpus_id"]
        metadata=metadatas[index]

        print("第", rank, "条结果")
        print("原召回排名：", index + 1)
        print("切片ID：", ids[index])
        print("重排序分数：", float(item["score"]))
        print("正文：", documents[index])
        print("来源编号：", metadata.get("source_id"))
        print("来源标题：", metadata.get("source_title"))
        print()



else:
    print("问题不能为空")
