from app.chunking import split_text,split_record,split_records
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