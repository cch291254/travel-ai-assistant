from app.chunking import split_text,split_record,split_records,same_merge_scope,is_merge_boundary,merge_short_records,merge_two_records

import pytest


def test_split_text_with_overlap():
    result=split_text(
        "abcdefghijklmnop",
        chunk_size=6,
        overlap=2,
    )

    assert result == [
        "abcdef",
        "efghij",
        "ijklmn",
        "mnop",
    ]

def test_split_none_text():
    result=split_text(
        ""
    )


    assert result==[]

def test_shrot_text():
    result=split_text(
        "杭州西湖",
        chunk_size=6,
        overlap=2,
    )

    assert result==["杭州西湖"]


def test_overlap_and_stop():
    result=split_text(
        "abcdefghij",
        chunk_size=6,
        overlap=2,
    )


    assert result==["abcdef","efghij"]

def test_split_blank_text():
    result = split_text("  \n\t  ")

    assert result == []


def test_invalid_chunk_size():
    with pytest.raises(ValueError,match="切片长度需大于0"):
        split_text("abc", chunk_size=0, overlap=0)

def test_invalid_overlap():
    with  pytest.raises(ValueError,match="重叠长度需大于等于0,且小于切片长度"):
        split_text("abc",chunk_size=6,overlap=-1)

def test_overlap_equal_to_chunk_size():
    with  pytest.raises(ValueError,match="重叠长度需大于等于0,且小于切片长度"):
            split_text("abc",chunk_size=6,overlap=6)

def test_overlap_greater_than_chunk_size():
    with  pytest.raises(ValueError,match="重叠长度需大于等于0,且小于切片长度"):
            split_text("abc",chunk_size=6,overlap=7)
    

def test_split_record_preserves_metadata():
    record = {
        "document_id": "hangzhou_routes",
        "source_id": "S05",
        "source": "data/raw/hangzhou_routes.md",
        "paragraph_index": 3,
        "page_number":2,
        "content": "abcdefghijklmnop",
        }
    result = split_record(record, chunk_size=6, overlap=2)
    second_result=split_record(record,chunk_size=6,overlap=2)
    first_ids = [chunk["chunk_id"] for chunk in result]
    second_ids = [chunk["chunk_id"] for chunk in second_result]


    assert len(result)==4
    assert result[0]["chunk_index"]==1
    assert result[3]["chunk_index"]==4
    assert result[0]["source_id"]=="S05"
    assert "chunk_index" not in record
    assert record["content"]== "abcdefghijklmnop"
    assert [chunk["content"] for chunk in result] == [
"abcdef",
"efghij",
"ijklmn",
"mnop",
]
    assert result[0]["chunk_id"]=='hangzhou_routes:page-2:paragraph-3:chunk-1'
    assert result[3]["chunk_id"]=='hangzhou_routes:page-2:paragraph-3:chunk-4'
    assert "chunk_id" not in record
    assert first_ids == second_ids

def test_split_records():
    records=[{"document_id": "hangzhou_routes",
            "source_id": "S05",
            "source": "data/raw/hangzhou_routes.md",
            "paragraph_index": 3,
            "page_number":2,
            "content": "abcdefghijklmnop",},{
            "document_id": "hangzhou_routes",
            "source_id": "S05",
            "source": "data/raw/hangzhou_routes.md",
            "paragraph_index": 4,
            "page_number":2,
            "content": "abcdefghijklmnop",}
             ]
    result=split_records(records,chunk_size=6,overlap=2)

    assert len(result) == 8
    assert result[0]["chunk_index"] == 1
    assert result[3]["chunk_index"] == 4
    assert result[4]["chunk_index"] == 1
    assert result[7]["chunk_index"] == 4
    assert result[0]["paragraph_index"] == 3
    assert result[4]["paragraph_index"] == 4
    assert result[0]["content"] == result[4]["content"]
    assert result[0]["chunk_id"] != result[4]["chunk_id"]


def test_split_records_skips_heading():
    records = [
        {
            "document_id": "test_document",
            "paragraph_index": 1,
            "content": "# S01 路线一",
            "heading_level": 1,
        },
        {
            "document_id": "test_document",
            "paragraph_index": 2,
            "content": "第一天游览西湖",
            "section_path": "S01 路线一",
            "section_level": 1,
        },
    ]

    result = split_records(records)

    assert len(result)==1
    assert result[0]["content"]=="第一天游览西湖"
    assert result[0]["section_path"]=="S01 路线一"
    assert result[0]["section_level"] == 1

def test_split_records_with_only_heading():
    records = [
        {
            "document_id": "test_document",
            "paragraph_index": 1,
            "content": "# S01 路线一",
            "heading_level": 1,
        }
    ]

    result = split_records(records)

    assert result == []

#测试是否合并
def test_same_merge_scope():
    left = {
        "document_id": "tour_products",
        "source_id": "SIM01",
        "section_path": "SIM01/P001",
        "valid_until": "2026-12-31",
    }

    # 1. 范围完全一致
    right = left.copy()
    assert same_merge_scope(left, right) is True

    # 2. 小节不同
    right["section_path"] = "SIM01/P002"
    assert same_merge_scope(left, right) is False

    # 3. 有效期不同
    right = left.copy()
    right["valid_until"] = "2027-12-31"
    assert same_merge_scope(left, right) is False

    # 4. 缺少必要的来源编号
    right = left.copy()
    del right["source_id"]
    assert same_merge_scope(left, right) is False


#测试合并有没有加入标题和冗余
def test_is_merge_boundary():
    # 标题不能跨过去合并
    assert is_merge_boundary({
        "content": "### 服务方式",
        "heading_level": 3,
    }) is True

    # 空内容和来源说明也是边界
    assert is_merge_boundary({"content": "   "}) is True
    assert is_merge_boundary({"content": "来源编号：SIM01"}) is True

    # 普通正文、列表本身不构成边界
    assert is_merge_boundary({"content": "成人票价为328元"}) is False
    assert is_merge_boundary({"content": "- 包含司机服务"}) is False


#测试段落合并情况
def test_merge_two_records():
    left = {
        "content": "第一段说明\n",
        "paragraph_index": 4,
        "source_id": "S06",
    }
    right = {
        "content": "\n第二段限制",
        "paragraph_index": 5,
        "source_id": "S06",
    }

    result = merge_two_records(left, right)

    assert result["content"] == "第一段说明\n\n第二段限制"
    assert result["paragraph_index"] == 4
    assert result["source_id"] == "S06"

    # 原始记录没有被修改
    assert left["content"] == "第一段说明\n"
    assert right["content"] == "\n第二段限制"
    assert result is not left

#测试切片是否正常进入
def test_merge_short_records_continuously():
    records = []

    for index, size in enumerate([20, 60, 120, 20], start=1):
        records.append({
            "document_id": "test_document",
            "source_id": "S01",
            "section_path": "S01/服务方式",
            "paragraph_index": index,
            "content": "文" * size,
        })

    result = merge_short_records(records)

    # 前三条：20 + 60 + 120 + 四个换行 = 204
    # 达到200，结束这一组
    assert len(result) == 2
    assert len(result[0]["content"]) == 204
    assert result[0]["paragraph_index"] == 1

    # 第四条单独保留，由循环结束后的收尾逻辑保存
    assert result[1]["content"] == "文" * 20
    assert result[1]["paragraph_index"] == 4

    # 原始记录不变
    assert len(records) == 4
    assert records[0]["content"] == "文" * 20


#遇到标题，要先保存待合并内容，不能跨标题继续拼。
def test_merge_short_records_stops_at_heading():
    first = {
        "document_id": "test_document",
        "source_id": "S01",
        "section_path": "S01/服务方式",
        "paragraph_index": 1,
        "content": "甲" * 20,
    }

    heading = {
        "content": "### 服务方式",
        "heading_level": 3,
    }

    last = first.copy()
    last["paragraph_index"] = 3
    last["content"] = "乙" * 60

    result = merge_short_records([first, heading, last])

    # 即使前后范围相同，也不能跨过标题合并
    assert len(result) == 3
    assert result[0]["content"] == "甲" * 20
    assert result[1]["content"] == "### 服务方式"
    assert result[2]["content"] == "乙" * 60