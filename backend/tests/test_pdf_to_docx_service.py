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
    # PAGEREF fields inside the pre-populated entries add their own begin marks, so the
    # TOC field is identified by the dirty flag that only the outer field carries.
    dirty_marks = [mark for mark in begin_marks if mark.get(qn("w:dirty")) == "true"]
    assert len(dirty_marks) == 1
    assert 'TOC \\o "1-6" \\h \\z \\u' in document.element.xml
    assert document.settings.element.find(qn("w:updateFields")) is not None


def test_toc_is_prepopulated_with_bookmarks_and_page_field():
    document = Document()
    document.add_heading("Chương Một", level=1)
    document.add_heading("Điều 1", level=2)
    pdf_to_docx_service.inject_table_of_contents(document)

    body = document.element.body
    xml = body.xml
    # Entries live between `separate` and `end`, so Word shows a TOC before any refresh.
    separate = [
        index
        for index, mark in enumerate(body.iter(qn("w:fldChar")))
        if mark.get(qn("w:fldCharType")) == "separate"
    ]
    ends = [
        index
        for index, mark in enumerate(body.iter(qn("w:fldChar")))
        if mark.get(qn("w:fldCharType")) == "end"
    ]
    assert separate and ends and separate[0] < ends[-1]
    assert xml.count("PAGEREF") == 2
    assert len(list(body.iter(qn("w:bookmarkStart")))) == 2
    assert " PAGE " in xml or any(
        " PAGE " in section.footer._element.xml for section in document.sections
    )


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


def test_layout_fallback_preserves_case_tables_and_toc_leaders():
    pdf_bytes = _pdf_with_table_and_toc()

    result = pdf_to_docx_service._convert_layout_fallback(pdf_bytes)
    reopened = Document(io.BytesIO(result))

    assert len(reopened.tables) == 1
    assert [[cell.text for cell in row.cells] for row in reopened.tables[0].rows] == [
        ["#", "Sprint", "Feature"],
        ["1", "Sprint Feature", "PDF"],
        ["2", "AI OCR", "DOCX"],
    ]
    toc = next(paragraph for paragraph in reopened.paragraphs if "\t1" in paragraph.text)
    assert toc.text == "1 Sprint Feature\t1"
    tab = toc._p.pPr.tabs.find(qn("w:tab"))
    assert tab.get(qn("w:val")) == "right"
    assert tab.get(qn("w:leader")) == "dot"
    assert len(reopened.paragraphs) == 1


def test_pdf_text_cleanup_removes_corrupt_markers_without_splitting_words():
    assert pdf_to_docx_service._clean_pdf_text("2 sAI OCR\ufffd") == "2 AI OCR"
    assert (
        pdf_to_docx_service._repair_spacing("Nền tảng Hạtầng Phụthuộc Trạngthái SplitF4")
        == "Nền tảng Hạtầng Phụ thuộc Trạng thái Split F4"
    )


def test_feature_matrix_rebuild_splits_columns_and_extracts_toc_data():
    rows = [
        pdf_to_docx_service._RebuiltTableRow(
            ["#", "Sprint Feature Mục tiêu chính", "Phụ thuộc Trạng thái", "", ""],
            [],
        ),
        pdf_to_docx_service._RebuiltTableRow(
            [
                "1",
                "Nền tảng & Tiện ích PDF F3 — Hạ tầng + đăng nhập + viewer ~70%",
                "S1 (viewer)",
                "",
                "",
            ],
            [],
        ),
    ]

    rebuilt = pdf_to_docx_service._rebuild_feature_matrix_rows(rows)

    assert rebuilt == [
        ["#", "Sprint", "Feature", "Mục tiêu chính", "Phụ thuộc", "Trạng thái"],
        [
            "1",
            "Nền tảng & Tiện ích PDF",
            "F3",
            "Hạ tầng + đăng nhập + viewer",
            "S1 (viewer)",
            "~70%",
        ],
    ]


def test_logical_table_rows_keeps_rows_without_numeric_key(monkeypatch):
    class _FakeRow:
        def __init__(self, cells):
            self.cells = cells

    class _FakeTable:
        def __init__(self, row_cells):
            self.rows = [_FakeRow(cells) for cells in row_cells]

    def rect(x0, y0, x1, y1):
        return (x0, y0, x1, y1)

    header = [rect(0, 0, 50, 10), rect(50, 0, 100, 10), rect(100, 0, 150, 10)]
    row_b = [rect(0, 10, 50, 20), rect(50, 10, 100, 20), rect(100, 10, 150, 20)]
    row_c = [rect(0, 20, 50, 30), rect(50, 20, 100, 30), rect(100, 20, 150, 30)]
    overflow = [rect(0, 30, 50, 40), rect(50, 30, 100, 40), rect(100, 30, 150, 40)]
    table = _FakeTable([header, row_b, row_c, overflow])

    texts = {
        header[0]: "Tên mặt hàng",
        header[1]: "Số lượng",
        header[2]: "Đơn giá",
        row_b[0]: "Bút bi",
        row_b[1]: "10",
        row_b[2]: "5000",
        row_c[0]: "Sách",
        row_c[1]: "2",
        row_c[2]: "15000",
        overflow[2]: "chuỗi",
    }
    monkeypatch.setattr(
        pdf_to_docx_service,
        "_text_in_rect",
        lambda _lines, cell: texts.get(tuple(cell), ""),
    )

    rows = pdf_to_docx_service._logical_table_rows(table, [])

    assert [(row.cells[0], row.cells[1], row.cells[2]) for row in rows] == [
        ("Tên mặt hàng", "Số lượng", "Đơn giá"),
        ("Bút bi", "10", "5000"),
        ("Sách", "2", "15000 chuỗi"),
    ]


def test_convert_to_docx_uses_fallback_when_pdf2docx_loses_case_and_table(monkeypatch):
    class BrokenConverter:
        def __init__(self, _pdf_path):
            pass

        def convert(self, docx_path, **_kwargs):
            document = Document()
            document.add_paragraph("sprint feature pdf")
            document.save(docx_path)

        def close(self):
            pass

    monkeypatch.setattr(pdf_to_docx_service, "Converter", BrokenConverter)
    result = pdf_to_docx_service.convert_to_docx(_pdf_with_table_and_toc())
    reopened = Document(io.BytesIO(result))

    assert len(reopened.tables) == 1
    assert reopened.tables[0].cell(0, 1).text == "Sprint"


def _save_pdf(pdf: fitz.Document) -> bytes:
    buffer = io.BytesIO()
    pdf.save(buffer)
    pdf.close()
    return buffer.getvalue()


def _pdf_with_table_and_toc() -> bytes:
    pdf = fitz.open()
    page = pdf.new_page(width=595, height=842)
    x_positions = [40, 100, 300]
    for row in [["#", "Sprint", "Feature"]]:
        for column_index, text in enumerate(row):
            page.insert_text(
                (x_positions[column_index], 100),
                text,
                fontname="helv",
                fontsize=10,
            )
    for row_index, row in enumerate(
        [
            ["s", "", ""],
            ["1", "Sprint Feature", "PDF"],
            ["s", "", ""],
            ["2", "AI OCR", "DOCX"],
        ],
        start=1,
    ):
        for column_index, text in enumerate(row):
            if text:
                page.insert_text(
                    (x_positions[column_index], 100 + row_index * 20),
                    text,
                    fontname="helv",
                    fontsize=10,
                )
    page.insert_text(
        (40, 280),
        "s........................................1",
        fontname="helv",
        fontsize=10,
    )
    page.insert_text(
        (40, 300),
        "1 Sprint Feature........................................1",
        fontname="helv",
        fontsize=10,
    )
    return _save_pdf(pdf)
