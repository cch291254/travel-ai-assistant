from pypdf import PdfReader
from pathlib import Path
from datetime import datetime
from pypdf.errors import PdfReadError

def parse_pdf_file(path_value):
    
    file_path=Path(path_value)
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在：{file_path}")
    if not file_path.is_file():
        raise ValueError(f"路径不是文件：{file_path}")
    supported_suffixes={".pdf"}
    if file_path.suffix.lower() not in supported_suffixes:
        raise ValueError(f"文件格式不支持：{file_path.suffix}")
    try:
        reader=PdfReader(file_path)
    except PdfReadError as error:
        raise ValueError(f"pdf解析失败:{file_path}") from error


    document_id=file_path.stem
    modified_time=file_path.stat().st_mtime
    updated_at=datetime.fromtimestamp(modified_time).isoformat(timespec="seconds")
    records=[]
    for page_number,page in enumerate(reader.pages,start=1):
        raw_text=page.extract_text()

        text=(raw_text or "").strip()
        if not text:
            print(f"第{page_number}页没有可提取的文字")
            continue

        record={"page_number":page_number,
        "content":text,
        "filename":file_path.name,
        "document_id":document_id,
        "source":file_path.as_posix(),
        "updated_at":updated_at}
        records.append(record)
    return records
if __name__ == "__main__":
    result = parse_pdf_file("data/raw/hangzhou_guide.pdf")

    for record in result:
        print(record)