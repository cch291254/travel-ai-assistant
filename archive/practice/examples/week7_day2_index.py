from app.ingest import parse_document
from app.source_metadata import add_source_id
from app.chunking import split_records
from app.embedding import load_embedding_model
from app.vector_store import get_vector_collection, upsert_chunks


records = parse_document("data/raw/hangzhou_routes.md")
enriched_records = add_source_id(records)
chunks = split_records(enriched_records)

model = load_embedding_model()
collection = get_vector_collection(
    name="travel_documents_bge_m3_titles_v4",
)

processed_count = upsert_chunks(chunks, model, collection)

print("本次处理切片数：", processed_count)
print("集合总记录数：", collection.count())
print("当前集合：", collection.name)