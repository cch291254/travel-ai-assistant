import chromadb


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