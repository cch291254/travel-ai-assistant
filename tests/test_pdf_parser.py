from app.pdf_parser import parse_pdf_file
from pypdf import PdfWriter
import pytest

def test_broken_pdf(tmp_path):
    file_path=tmp_path/"empty.pdf"
    file_path.write_text("这不是真正的pdf",encoding="utf-8")
    with pytest.raises(ValueError,match="pdf解析失败"):
        parse_pdf_file(file_path)
def test_empty_pdf_page(tmp_path):
    file_path=tmp_path/"empty.pdf"
    writer=PdfWriter()
    writer.add_blank_page(width=595,height=842)
    with file_path.open("wb") as pdf_file:
        writer.write(pdf_file)
    records=parse_pdf_file(file_path)
    assert records==[]
#验证无内容pdf

def test_parse_pdf():
    records=parse_pdf_file("data/raw/hangzhou_guide.pdf")


    assert len(records)==2
    assert records[0]["page_number"]==1
    assert "杭州旅行提示" in records[0]["content"]
    assert records[1]["page_number"]==2
    assert "出行建议" in records[1]["content"]