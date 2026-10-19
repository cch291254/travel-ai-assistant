

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


def add_source_id(records):
    enriched_records = []
    current_source_id=None
    current_valid_from = None
    current_valid_until = None
    current_heading_level=None
    heading_titles = [None] * 6
    current_section_path = None
    current_source_title = None

    for record in records:
        content=record["content"]
        heading_level=record.get("heading_level")

        if heading_level is not None:
            title=content[heading_level:].strip()
            current_heading_level = heading_level
            heading_titles[heading_level-1]=title
            #列表形态[chunk,none,none,noen,none,noe]
            for i in range(heading_level,6):
                heading_titles[i]=None

            path_titles=[]
            for heading_title in heading_titles:
                if heading_title is not None:
                    path_titles.append(heading_title)
            #示例path_title：千岛湖路线资料 / 套餐2
            current_section_path="/".join(path_titles)
            source_id=extract_source_id(content)

            if source_id is not None:
                current_source_id=source_id
                current_source_title = title
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
        record_with_source["valid_from"] = current_valid_from
        record_with_source["valid_until"] = current_valid_until
        record_with_source["section_level"] = current_heading_level
        record_with_source["section_path"] = current_section_path
        record_with_source["source_title"] = current_source_title

        enriched_records.append(record_with_source)

    return enriched_records


if __name__ == "__main__":
    text = "生效日期：2026-09-28\n有效期至：2026-12-31"
    print(extract_validity(text))
    print(extract_validity("没有提供日期"))
    print(extract_validity("生效日期未提供"))