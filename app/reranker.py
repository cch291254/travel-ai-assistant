from sentence_transformers import CrossEncoder


#配置向量模型，配置gpu，本地运行
def load_reranker():
    reranker=CrossEncoder(
        "BAAI/bge-reranker-v2-m3",
        device="cuda",
        local_files_only=True,
    )

    reranker.max_seq_length=512
    reranker.half()
    return reranker



def rerank_chunks(question,results,reranker,top_k=3):
    if top_k<=0:
        raise ValueError("返回数量必须大于0")

    documents=results["documents"][0]
    metadatas=results["metadatas"][0]
    ids=results["ids"][0]

    if not documents:
        return []

    rerank_texts=[]
    for index, document in enumerate(documents):
        metadata=metadatas[index]
        section_path=metadata.get("section_path","")
        #组合单条章节名字和正文
        rerank_texts.append(section_path+"\n"+document)

#重排列
    ranked=reranker.rank(
        question,
        rerank_texts,
        top_k=len(rerank_texts),
        batch_size=2
    )
    #查看召回排序问题
    # for rank, item in enumerate(ranked, start=1):
    #     index = item["corpus_id"]
    #     print("重排完整排名：", rank,
    #         "分数：", float(item["score"]),
    #         "片段：", ids[index])
    #     print(documents[index])


    evidence=[]

#去掉文档和章节重复的排列
    for rerank_rank,item in enumerate(ranked,start=1):
        index=item["corpus_id"]
        metadata=metadatas[index]

        evidence.append({
            "chunk_id":ids[index],
            "content":documents[index],
            "metadata":metadata,
            "retrieval_rank":index+1,
            "rerank_rank":rerank_rank,
            "rerank_score":float(item["score"])
        })

        if len(evidence)==top_k:
            break

    return evidence