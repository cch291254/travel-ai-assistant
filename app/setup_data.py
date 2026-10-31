from pathlib import Path

from huggingface_hub import snapshot_download

from app.chunking import split_records
from app.ingest import parse_document
from app.source_metadata import add_source_id
from app.vector_store import get_vector_collection, upsert_chunks


RAW_DIR = "data/raw"
COLLECTION_NAME = "travel_documents_full_20161014_v2"
MODEL_REPOS = ("BAAI/bge-m3", "BAAI/bge-reranker-v2-m3")
IGNORED_MODEL_FILES = ["onnx/*", "imgs/*"]


def download_models():
    for repo in MODEL_REPOS:
        print("准备模型：", repo)
        snapshot_download(repo, ignore_patterns=IGNORED_MODEL_FILES)


def collect_chunks(raw_dir):
    all_chunks = []
    for file_path in sorted(Path(raw_dir).glob("*.md")):
        records = add_source_id(parse_document(file_path))
        chunks = split_records(records, chunk_size=400, overlap=80)
        all_chunks.extend(chunks)
        print(file_path.name, "切片数：", len(chunks))
    return all_chunks


def build_index():
    collection = get_vector_collection(name=COLLECTION_NAME)
    if collection.count() != 0:
        print("向量库已有数据，跳过入库：", collection.count())
        return

    chunks = collect_chunks(RAW_DIR)

    # 只在需要入库时才加载模型，已有向量库时不用占内存。
    from app.embedding import load_embedding_model

    upsert_chunks(chunks, load_embedding_model(), collection)

    # 空集合不会报错，只会让模型回答“资料里没有”，所以这里必须检查。
    if collection.count() == 0:
        raise RuntimeError("入库后向量库仍然为空，请检查 data/raw")
    print("入库完成，向量库切片数：", collection.count())


if __name__ == "__main__":
    download_models()
    build_index()
