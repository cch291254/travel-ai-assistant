from sentence_transformers import SentenceTransformer
import chromadb

#模型添加
model=SentenceTransformer(
    "BAAI/bge-m3",
    device="cuda"
)

model.max_seq_length=512
model.half()

texts=[
    "杭州三日游有哪些景点？",
    "杭州三日游可以游览西湖、灵隐寺和雷峰塔。",
    "电脑无法开机，需要检查电源。",
    "北京三日游可以参观故宫和长城。",
]

vectors=model.encode(
    texts,
    batch_size=4,
    normalize_embeddings=True
)
#添加向量库
client = chromadb.PersistentClient(path="data/chroma")

collection = client.get_or_create_collection(
    name="travel_chunks",
    configuration={
        "hnsw": {
            "space": "cosine"
        }
    },
)

collection.upsert(
    ids=["hangzhou", "computer", "beijing"],
    documents=texts[1:],
    embeddings=vectors[1:].tolist(),
)

results=collection.query(
    query_embeddings=[vectors[0].tolist()],
    n_results=3,
)
