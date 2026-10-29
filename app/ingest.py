from pathlib import Path
from app.document_parser import parse_text_file
from app.pdf_parser import parse_pdf_file
import hashlib
from app.document_store import register_document
from datetime import datetime


#当前支持的资料扩展名
ALLOWED_DOCUMENT_SUFFIXES={".md",".txt",".pdf"}

#单份资料限制
MAX_DOCUMENT_BYTES=10*1024*1024
def validate_document_file(path_value):
    file_path=Path(path_value)

    suffix=file_path.suffix.lower()  #那文件名
    if suffix not in ALLOWED_DOCUMENT_SUFFIXES:
        raise ValueError(f"不支持的文件格式:{suffix}")

    #确认是否是文件
    if not file_path.is_file():
        raise FileNotFoundError(f"资料文件不存在或不是文件：{file_path}")

    #只读取文件大小
    if file_path.stat().st_size>MAX_DOCUMENT_BYTES:
        raise ValueError("单份资料不能超过10 MiB")

    return file_path

def parse_document(path_value):
    file_path=validate_document_file(path_value)
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

    #当前还未进行文件检查
    file_hash=None
    updated_at=None

    try:
        # 先检查，再读取文件计算哈希、解析正文。
        file_path = validate_document_file(file_path)
        updated_at = datetime.fromtimestamp(
            file_path.stat().st_mtime
        ).isoformat(timespec="seconds")

        file_hash = calculate_file_hash(file_path)
        records = parse_document(file_path)

    except (ValueError, FileNotFoundError) as error:
        # 保留失败登记；校验未通过时，哈希为空。
        register_document(
            conn, file_path.name, str(file_path),
            file_hash, updated_at, "failed", str(error),
        )
        return {
            "status": "failed",
            "records": [],
            "error": str(error),
        }

    #
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

def ingest_directory(conn,path_value):
    directory_path=Path(path_value)
    if not directory_path.exists():
        raise FileNotFoundError(f"目录不存在:{directory_path}")
    if not directory_path.is_dir():
        raise ValueError(f"不是目录：{directory_path}")
    summary={"success":0,"failed":0,"skipped":0}
    for file_path in sorted(directory_path.iterdir()):
        if not file_path.is_file():
            continue
        result=ingest_file(conn,file_path)
        status=result["status"]
        summary[status]+=1
    return summary

    