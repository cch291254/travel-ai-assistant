

def extract_source_id(content):
    text=content.lstrip("#").strip()
    text = text.replace("｜", " ")
    text = text.replace("|", " ")
    words=text.split()
    if words==[]:
        return None

    
    source_id=words[0].upper()
    is_source_id=((
        source_id.startswith("S")
        and source_id[1:].isdigit())
        or
        (source_id.startswith("SIM")
        and source_id[3:].isdigit())
    )
    if is_source_id:
        return source_id
    else:
        return None

def add_source_id(records,document_type=None):
    enriched_records = []
    current_source_id=None
    current_title=None
    current_valid_from = None
    current_valid_until = None
    current_heading_level=None

    for record in records:
        content=record["content"]
        heading_level=record.get("heading_level")
        if heading_level is not None:
            title=content[heading_level:].strip()
            current_title=title    
            current_heading_level = heading_level
            source_id=extract_source_id(content)
            if source_id is not None:
                current_source_id=source_id
                current_valid_from = None
                current_valid_until = None
        dates=extract_validity(content)
        if dates["valid_from"] is not None:
            current_valid_from=dates["valid_from"]
        if dates["valid_until"] is not None:
            current_valid_until=dates["valid_until"]
        record_with_source=record.copy()   
        record_with_source["source_date"] = None
        record_with_source["source_id"]=current_source_id
        record_with_source["section_title"]=current_title
        record_with_source["document_type"]=document_type
        record_with_source["valid_from"] = current_valid_from
        record_with_source["valid_until"] = current_valid_until
        record_with_source["section_level"] = current_heading_level
        enriched_records.append(record_with_source)

    return enriched_records

def extract_validity(content):
    dates = {
        "valid_from": None,
        "valid_until": None,
    }

    for line in content.splitlines():
        line = line.strip()
        if line.startswith("生效日期："):
            dates["valid_from"]=line.split("：", 1)[1].strip()
        if line.startswith("有效期至："):
            dates["valid_until"]=line.split("：", 1)[1].strip()
    
    return dates
if __name__ == "__main__":
    text = "生效日期：2026-09-28\n有效期至：2026-12-31"
    print(extract_validity(text))
    print(extract_validity("没有提供日期"))
    print(extract_validity("生效日期未提供"))