import chromadb
from sentence_transformers import CrossEncoder


client = chromadb.PersistentClient(path="data/chroma")
collection = client.get_collection(
    name="travel_documents_bge_m3_titles_v3",
)

question = "午餐费用包含吗？"

candidate_ids = [
    "hangzhou_routes:paragraph-26:chunk-1",
    "hangzhou_routes:paragraph-24:chunk-3",
]

pairs = []

for chunk_id in candidate_ids:
    record = collection.get(ids=[chunk_id])

    document = record["documents"][0]
    metadata = record["metadatas"][0]
    text = metadata["section_path"] + "\n" + document

    pairs.append((question, text))

reranker = CrossEncoder(
    "BAAI/bge-reranker-v2-m3",
    device="cuda",
)
reranker.max_seq_length = 512
reranker.half()

scores = reranker.predict(pairs, batch_size=2)

for index, score in enumerate(scores):
    print("切片：", candidate_ids[index])
    print("重排序分数：", float(score))
    print()