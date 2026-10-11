from app.source_metadata import add_source_id,extract_source_id


def test_add_source_id():
    records = [
    {"content": "文档说明", "heading_level": None},
    {"content": "# s01 路线一", "heading_level": 1},
    {"content": "第一天游西湖", "heading_level": None},
    {"content": "### 详细行程", "heading_level": 3},
    {"content": "第二天游灵隐", "heading_level": None},
    {"content": "## s02｜路线二", "heading_level": 2},
    {"content": "另一条路线的安排", "heading_level": None},
]
    source_ids=[]
    section_titles=[]
    enriched_reocrds=add_source_id(records)
    for record in enriched_reocrds:
        source_id=record["source_id"]
        section_title=record["section_title"]
        source_ids.append(source_id)
        section_titles.append(section_title)

    assert source_ids==[None, "S01", "S01", "S01", "S01", "S02", "S02"]
    assert section_titles==[
    None,
    "s01 路线一",
    "s01 路线一",
    "详细行程",
    "详细行程",
    "s02｜路线二",
    "s02｜路线二",
]
    for record in records:
        assert "source_id" not in record
        assert "section_title" not in record

def test_extract_sorce_id():
    records= [
        {"content": "文档说明"},
        {"content": "# s01 路线一"},
        {"content": "第一天游西湖"},
        {"content": "### SIM01 详细行程"},
        {"content": "# SIM01 第二天游灵隐"},
        {"content": "## s02｜路线二"},
        {"content": "另一条路线的安排"},
    ]
    source_ids=[]
    for record in records:
        content=record["content"]
        source_id=extract_source_id(content)
        source_ids.append(source_id)
    assert source_ids==[None,"S01",None,"SIM01","SIM01","S02",None]

def test_validity_inherits_and_resets():
    records = [
    {"content": "# SIM01 模拟产品", "heading_level": 1},
    {"content": "生效日期：2026-09-28\n有效期至：2026-12-31"},
    {"content": "模拟产品正文"},
    {"content": "### 费用包含", "heading_level": 3},
    {"content": "模拟产品费用说明"},
    {"content": "## S05 真实产品", "heading_level": 2},
    {"content": "未提供有效期的真实产品正文"},
]
    result = add_source_id(records, document_type="product")

    assert result[2]["valid_from"]=="2026-09-28"
    assert result[2]["valid_until"]=="2026-12-31"
    assert result[4]["valid_from"]=="2026-09-28"
    assert result[4]["valid_until"]=="2026-12-31"
    assert result[6]["valid_from"]==None
    assert result[6]["valid_until"]==None
    assert result[6]["document_type"]=="product"
    assert result[6]["source_id"] == "S05"
    assert result[2]["section_level"] == 1
    assert result[4]["section_level"] == 3
    assert result[6]["section_level"] == 2

