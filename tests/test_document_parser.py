from app.document_parser import parse_text_file
import pytest


def test_file_not_found(tmp_path):
    missing_file=tmp_path/"missing.txt"
    with pytest.raises(FileNotFoundError,match="文件不存在"):
        parse_text_file(missing_file)
def test_file_not_right(tmp_path):
    with pytest.raises(ValueError,match="路径不是文件"):
        parse_text_file(tmp_path)
        
def test_file_not_sup(tmp_path):
    file_path = tmp_path / "sample.json"
    file_path.write_text("一。\n\n二。",encoding="utf-8")
    with pytest.raises(ValueError,match="不支持的文件格式"):
        parse_text_file(file_path)
def test_parse_markdoen(tmp_path):
    file_path=tmp_path/"guide.md"
    file_path.write_text("#标题。\n\n正文内容。",encoding="utf-8")
    records=parse_text_file(file_path)
    assert records[0]["content"]=="#标题。"
    assert records[1]["content"]=="正文内容。"
    assert records[0]["filename"]=="guide.md"
def test_empty_file(tmp_path):
    file_path=tmp_path/"empty.txt"
    file_path.write_text("")
    records=parse_text_file(file_path)
    assert records==[]
def test_parse_tst(tmp_path):
    file_path=tmp_path/"sample.txt"
    file_path.write_text("内容一。\n\n内容二。",encoding="utf-8")
    records=parse_text_file(file_path)
    expected_keys = {
    "document_id",
    "filename",
    "paragraph_index",
    "content",
    "source",
    "updated_at",}


    assert set(records[0]) == expected_keys
    assert len(records)==2
    assert records[0]["filename"]=="sample.txt"
    assert records[0]["paragraph_index"]==1
    assert records[0]["content"] == "内容一。"
    assert records[1]["paragraph_index"] == 2
    assert records[1]["content"] == "内容二。"