from pathlib import Path
from app.ingest import parse_document
from app.source_metadata import add_source_id
from app.chunking import split_records

from app.embedding import load_embedding_model
from app.vector_store import get_vector_collection, upsert_chunks

#进行多文件切片
def collect_chunks(raw_dir):
    directory=Path(raw_dir)
    files=sorted(directory.glob("*.md"))

    all_chunks=[]
    for file_path in files:
        records=parse_document(file_path)
        enriched_records=add_source_id(records)
        chunks=split_records(enriched_records,chunk_size=400,overlap=80)

        all_chunks.extend(chunks)
        print(file_path.name, "切片数：", len(chunks))
    return all_chunks




if __name__ == "__main__":
    chunks = collect_chunks("data/raw")
    print("总切片数：", len(chunks))



    collection=get_vector_collection(
        name="travel_documents_full_20161014_v2"
    )
    if collection.count()!=0:
        raise ValueError("当前集合已有数据，请先检查，不要继续写入")

    model=load_embedding_model()
    processed_count=upsert_chunks(chunks,model,collection)

    print("写入切片数：", processed_count)
    print("集合当前数量：", collection.count())