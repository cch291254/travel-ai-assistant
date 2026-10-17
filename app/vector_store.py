import chromadb

#获取或创建指定名称的持久化向量集合
def get_vector_collection(name="travel_chunks"):
    client=chromadb.PersistentClient(path="data/chroma")

    collection=client.get_or_create_collection(
        name=name,
        configuration={
            "hnsw":{
                "space":"cosine"
            }
        },
    )

    return collection


#存向量库
def upsert_chunks(chunks,model,collection):
    if not chunks:
        return 0

    ids=[]
    documents=[]
    metadatas=[]
    embedding_texts=[]


    for chunk in chunks:
        ids.append(chunk["chunk_id"])
        documents.append(chunk["content"])
        section_path=chunk.get("section_path")
        embedding_text=chunk["content"]

        if section_path:
            embedding_text=section_path+"\n"+embedding_text

        embedding_texts.append(embedding_text)
        metadata={}

        for key,value in chunk.items():
            if key in ("chunk_id","content"):
                continue

            if value is None:
                continue

            metadata[key]=value

        metadatas.append(metadata)

    vectors=model.encode(
        embedding_texts,
        batch_size=4,
       normalize_embeddings=True
    )

    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=vectors.tolist(),
        metadatas=metadatas
    )

    return len(ids)

#召回向量
def query_chunks(question,model,collection,n_results=3,where=None):
    question=question.strip()

    if not question:
        raise ValueError("问题不能为空")

    query_vectors=model.encode(
        [question],
        normalize_embeddings=True,
    )

    results=collection.query(
        query_embeddings=query_vectors.tolist(),
        n_results=n_results,
        where=where,
    )

    return results

# 查询指定文档的全部切片 ID
def get_document_chunk_ids(document_id, collection):
    if not isinstance(document_id, str) or not document_id.strip():
        raise ValueError("文档 ID 必须是非空字符串")

    result = collection.get(
        where={"document_id": document_id.strip()}
    )

    return result["ids"]

#删除指定文档切片
def delete_document_chunks(document_id,collection):
    ids=get_document_chunk_ids(document_id,collection)

    if not ids:
        return 0
    collection.delete(ids=ids)

    return len(ids)

#添加新切片
def replace_document_chunks(document_id,chunks,model,collection):
    if not chunks:
        raise ValueError("新切片不能为空,删除文档请使用删除函数")

    old_ids=set(get_document_chunk_ids(document_id,collection))
    new_ids=set()


    for chunk in chunks:
        if chunk["document_id"]!=document_id.strip():
            raise ValueError("新切片需为指定文档切片")
        new_ids.add(chunk["chunk_id"])

    if len(new_ids) !=len(chunks):
        raise ValueError("新切片ID不能重复")
    #添加的是整个更新的文档
    written=upsert_chunks(chunks,model,collection)
#看看有没有多余剩下的切片
    stale_ids=sorted(old_ids-new_ids)
    if stale_ids:
        collection.delete(ids=stale_ids)

    return{
        "written":written,
        "deleted":len(stale_ids),
    }

