import io

import pymupdf as fitz
from docx import Document
from docx.oxml.ns import qn

from app.services import pdf_to_docx_service


def _pdf_with_outline() -> bytes:
    pdf = fitz.open()
    page1 = pdf.new_page(width=595, height=842)
    page1.insert_text((72, 72), "CHƯƠNG I", fontsize=18, fontname="helv")
    page1.insert_text((72, 100), "1.1 Phạm vi", fontsize=14, fontname="helv")
    page1.insert_text((72, 130), "Nội dung bình thường.", fontsize=11, fontname="helv")
    toc = [
        [1, "CHƯƠNG I", 1],
        [2, "1.1 Phạm vi", 1],
    ]
    pdf.set_toc(toc)
    buffer = io.BytesIO()
    pdf.save(buffer)
    pdf.close()
    return buffer.getvalue()


def test_read_pdf_outlines_returns_name_and_level():
    outlines = pdf_to_docx_service.read_pdf_outlines(_pdf_with_outline())
    assert [(item.title, item.level) for item in outlines] == [
        ("CHƯƠNG I", 1),
        ("1.1 Phạm vi", 2),
    ]


def test_apply_word_styles_uses_outline_before_font_size():
    pdf_bytes = _pdf_with_outline()
    document = Document()
    document.add_paragraph("CHƯƠNG I")
    document.add_paragraph("1.1 Phạm vi")
    document.add_paragraph("Nội dung bình thường.")
    buffer = io.BytesIO()
    document.save(buffer)

    result = pdf_to_docx_service.apply_word_styles(
        buffer.getvalue(),
        pdf_bytes=pdf_bytes,
    )
    reopened = Document(io.BytesIO(result))

    heading_by_text = {
        paragraph.text: paragraph.style.name for paragraph in reopened.paragraphs if paragraph.text
    }
    assert heading_by_text["CHƯƠNG I"] == "Heading 1"
    assert heading_by_text["1.1 Phạm vi"] == "Heading 2"
    assert heading_by_text["Nội dung bình thường."] == "Normal"


def test_toc_field_contains_dirty_and_update_setting():
    document = Document()
    document.add_heading("Chương Một", level=1)
    document.add_heading("Điều 1", level=2)
    pdf_to_docx_service.inject_table_of_contents(document)

    begin_marks = [
        mark
        for mark in document.element.body.iter(qn("w:fldChar"))
        if mark.get(qn("w:fldCharType")) == "begin"
    ]
    assert len(begin_marks) == 1
    assert begin_marks[0].get(qn("w:dirty")) == "true"
    assert 'TOC \\o "1-3" \\h \\z \\u' in document.element.xml
    assert document.settings.element.find(qn("w:updateFields")) is not None


def test_fallback_regex_marks_chapter_article_and_numbered_headings():
    document = Document()
    document.add_paragraph("CHƯƠNG I")
    document.add_paragraph("Điều 1. Phạm vi")
    document.add_paragraph("1.2.3 Chi tiết")
    buffer = io.BytesIO()
    document.save(buffer)

    pdf = fitz.open()
    pdf.new_page(width=595, height=842)
    result = pdf_to_docx_service.apply_word_styles(
        buffer.getvalue(),
        pdf_bytes=_save_pdf(pdf),
    )
    reopened = Document(io.BytesIO(result))

    heading_by_text = {
        paragraph.text: paragraph.style.name for paragraph in reopened.paragraphs if paragraph.text
    }
    assert heading_by_text["CHƯƠNG I"] == "Heading 1"
    assert heading_by_text["Điều 1. Phạm vi"] == "Heading 2"
    assert heading_by_text["1.2.3 Chi tiết"] == "Heading 3"


def _save_pdf(pdf: fitz.Document) -> bytes:
    buffer = io.BytesIO()
    pdf.save(buffer)
    pdf.close()
    return buffer.getvalue()
