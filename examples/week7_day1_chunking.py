from app.ingest import parse_document
from app.chunking import split_records
from app.source_metadata import add_source_id
from pprint import pprint


records = parse_document("data/raw/hangzhou_routes.md")
enriched_records = add_source_id(records,document_type="route")
chunks = split_records(enriched_records)

print("records数量：", len(records))
print("chunks数量：", len(chunks))

for chunk in chunks:
    if chunk["source_id"] is not None:
        pprint(chunk)
        break