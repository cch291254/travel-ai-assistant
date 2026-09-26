from pathlib import Path
from app.document_parser import parse_text_file
from app.pdf_parser import parse_pdf_file
import hashlib
from app.document_store import register_document
from datetime import datetime

def parse_document(path_value):
    file_path=Path(path_value)
    suffix=file_path.suffix.lower()
    if suffix in {".md",".txt"}:
        return parse_text_file(file_path)
    elif suffix==".pdf":
        return parse_pdf_file(file_path)
    else:
        raise ValueError(f"不支持的文件格式:{suffix}")
def calculate_file_hash(path_value):
    file_path=Path(path_value)
    file_bytes=file_path.read_bytes()
    return hashlib.sha256(file_bytes).hexdigest()
def ingest_file(conn,path_value):
    file_path=Path(path_value)
    file_hash=calculate_file_hash(file_path)
    updated_at = datetime.fromtimestamp(
        file_path.stat().st_mtime
).isoformat(timespec="seconds")
    try:
        records=parse_document(file_path)
    except ValueError as error:
        register_document(conn,file_path.name,str(file_path),file_hash,updated_at,"failed",str(error))
        return {"status":"failed","records":[],"error":str(error),}
    registered=register_document(conn,file_path.name,
        str(file_path),
        file_hash,
        updated_at,
        "success",)
    if registered:
        return {"status":"success",
        "records":records}
    return {"status":"skipped",
    "records":[]}

    