
from app.document_store import init_db,register_document
def test_Init_db():
    conn=init_db(":memory:")
    result=conn.execute("""
    SELECT name FROM sqlite_master WHERE type=? and name=?""",("table","documents")).fetchone()
    
    assert result==("documents",)
    conn.close()
def test_register_document_success():
    
    conn=init_db(":memory:")
    result=register_document(
        conn,"test.pdf",
        "data/raw/test.pdf",
        "hash_001",
        "2026-09-24T10:00:00",
        "success",)

    record=conn.execute("select filename,file_hash,status,error_message FROM documents").fetchone()
    assert result  is True
    assert record==("test.pdf","hash_001","success",None)
    conn.close()

def test_register_document_duplicate():
    conn=init_db(":memory:")
    result_01=register_document(
        conn,"test_01.pdf",
        "data/raw/test_01.pdf",
        "hash_001",
        "2026-09-24T10:00:00",
        "success",)
    result_02=register_document(
        conn,"test_02.pdf",
        "data/raw/tes_02.pdf",
        "hash_001",
        "2026-09-24T10:00:00",
        "success",)
    record=conn.execute("SELECT*FROM documents").fetchone()
    count=conn.execute("select count(*) from documents").fetchone()
    assert result_01 is True
    assert result_02 is False
    assert count== (1,)
    assert record==(1, 'test_01.pdf', 'data/raw/test_01.pdf', 'hash_001', '2026-09-24T10:00:00', 'success', None)
    conn.close()
def test_register_failed_document():
    conn=init_db(":memory:")
    result=register_document(conn,"broken.pdf",
    "data/raw/broken.pdf",
    None,
    None,
"failed",
 "PDF解析失败")
    record = conn.execute(
    """SELECT status, error_message
    FROM documents
    WHERE filename = ?""",
    ("broken.pdf",),
).fetchone()

    assert result is True
    assert record == ("failed", "PDF解析失败")
    conn.close()