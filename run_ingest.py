from app.document_store import init_db, get_document_status
from app.ingest import ingest_directory


conn = init_db("data/real_documents.db")

summary = ingest_directory(conn,"data/raw")
status_counts = get_document_status(conn)

print("本次导入结果：", summary)
print("数据库累计状态：", status_counts)

conn.close()