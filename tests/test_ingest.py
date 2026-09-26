import pytest
from app.ingest import parse_document, calculate_file_hash, ingest_file
from app.document_store import init_db

def test_parse_document_txt(tmp_path):
    file_path=tmp_path/"samplel.txt"
    file_path.write_text("第一段。\n\n第二段。",encoding="utf-8")
    result=parse_document(file_path)
    assert len(result)==2
def test_parse_not_document(tmp_path):
    file_path=tmp_path/"sample.json"
    with pytest.raises(ValueError,match="不支持的文件格式"):
        parse_document(file_path)
def test_parse_document_pdf():
    file_path="data/raw/hangzhou_guide.pdf"
    result=parse_document(file_path)
    assert len(result)>0
def test_caiculate_file_hash_same_content(tmp_path):
    first_path=tmp_path/"test01.txt"
    first_path.write_text("第一段。\n\n第二段。",encoding="utf-8")
    frist_hash=calculate_file_hash(first_path)
    second_path=tmp_path/"test02.txt"
    second_path.write_text("第一段。\n\n第二段。",encoding="utf-8")
    second_hash=calculate_file_hash(second_path)
    assert frist_hash==second_hash
    assert len(frist_hash)==64
def test_ingest_file_success(tmp_path):
    file_path=tmp_path/"sample.txt"
    file_path.write_text("第一段。\n\n第二段。",encoding="utf-8")
    conn=init_db(":memory:")
    result=ingest_file(conn,file_path)
    record=conn.execute("select filename,status from documents").fetchone()
    assert result["status"]=="success"
    assert len(result["records"])==2
    assert record==("sample.txt","success")
    conn.close()
def test_ingest_file_duplicate(tmp_path):
    first_path=tmp_path/"test1.txt"
    secend_path=tmp_path/"test2.txt"
    first_path.write_text("第一段。\n\n第二段。",encoding="utf-8")
    secend_path.write_text("第一段。\n\n第二段。",encoding="utf-8")
    conn=init_db(":memory:")
    first_result=ingest_file(conn,first_path)
    secend_result=ingest_file(conn,secend_path)
    count=conn.execute("select count(*) from documents").fetchone()
    assert first_result["status"]=="success"
    assert secend_result["status"]=="skipped"
    assert secend_result["records"]==[]
    assert count==(1,)
    conn.close()
def test_ingest_file_failed(tmp_path):
    file_path=tmp_path/"sample.json"
    file_path.write_text("{}",encoding="utf-8")
    conn=init_db(":memory:")
    result=ingest_file(conn,file_path)
    record = conn.execute(
    """
    SELECT status, error_message
    FROM documents
    WHERE filename = ?
    """,
    ("sample.json",),
).fetchone()

    assert record == ("failed", "不支持的文件格式:.json")
    assert result["status"]=="failed"
    assert result["records"]==[]
    assert result["error"]=="不支持的文件格式:.json"
    conn.close()