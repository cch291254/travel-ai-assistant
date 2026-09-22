from pathlib import Path
from datetime import datetime
def parse_text_file(path_value):
    file_path=Path(path_value)
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在：{file_path}")
    if not file_path.is_file():
        raise ValueError(f"路径不是文件:{file_path}")
    supported_suffixes={".txt",".md"}
    if file_path.suffix.lower() not in supported_suffixes:
        raise ValueError(f"不支持的文件格式：{file_path.suffix}")

    content=file_path.read_text(encoding="utf-8")    
    parts=content.split("\n\n")
    paragraphs=[]
    for part in parts:
        clean_part=part.strip()
        if clean_part:
            paragraphs.append(clean_part)

    document_id=file_path.stem
    modified_time=file_path.stat().st_mtime
    updated_at=datetime.fromtimestamp(modified_time).isoformat(timespec="seconds")
    records=[]
    for paragraph_index,paragraph in enumerate(paragraphs,start=1):
        record={"filename":file_path.name,
        "paragraph_index":paragraph_index,
        "content":paragraph,
        "document_id":document_id,
        "source":file_path.as_posix(),
        "updated_at":updated_at}
        
        records.append(record)
    
    return  records
if __name__ == "__main__":
    result = parse_text_file("data/raw/hangzhou_guide.md")
    for record in result:
        print(record)
