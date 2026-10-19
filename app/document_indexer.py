from pathlib import Path

from app.ingest import parse_document,calculate_file_hash
from app.source_metadata import add_source_id
from app.chunking import split_records
from app.vector_store import replace_document_chunks
from app.document_store import save_document_index
from app.vector_store import delete_document_chunks
from app.document_store import delete_document_index

#单文档索引入口
def index_document(path_value,model,collection):
    file_path=Path(path_value)
    document_id=file_path.stem

    records=parse_document(file_path)

    enriched_records=add_source_id(records)

    chunks=split_records(
        enriched_records,
        chunk_size=400,
        overlap=80,
        )

    result=replace_document_chunks(
        document_id,chunks,model,collection,
    )

    return {
        "document_id":document_id,   
        "written":result["written"],  #写入的
        "deleted":result["deleted"] #删掉的切片
    }

#保存进入db
def index_document_with_registration(
        path_value,model,collection,conn
):
    file_path=Path(path_value)
    file_hash=calculate_file_hash(file_path)

    result=index_document(file_path,model,collection)

    save_document_index(
        conn,
        collection.name,
        result["document_id"],
        str(file_path.resolve()), #返回字符串，绝对路径
        file_hash,
    )

    return result

#先删除向量切片，成功后再删除 SQL 登记
def delete_document_with_registration(document_id,collection,conn):
    delete_chunks=delete_document_chunks(document_id,collection)

    delete_registration=delete_document_index(conn,collection.name,document_id.strip())

    return {
        "document_id":document_id.strip(),
        "deleted_chunks":delete_chunks,   #删除了哪些
        "deleted_registration":delete_registration   #删除了几片
    }