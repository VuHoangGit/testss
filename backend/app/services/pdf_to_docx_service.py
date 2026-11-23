"""Export PDF sang DOCX bằng layout thực + hậu xử lý Heading/TOC.

Luồng:
1. PyMuPDF đọc outline và metadata font của PDF.
2. pdf2docx chuyển PDF thành DOCX tạm để giữ layout/bảng/font.
3. python-docx gán Heading 1-3 và chèn TOC field động.
"""

from __future__ import annotations

import io
import re
import tempfile
import warnings
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

warnings.filterwarnings(
    "ignore",
    message=r"The `fitz` API is deprecated",
    category=FutureWarning,
)

import pymupdf as fitz  # noqa: E402
from docx import Document  # noqa: E402
from docx.oxml import OxmlElement  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from pdf2docx import Converter  # noqa: E402


@dataclass(frozen=True)
class PdfOutline:
    title: str
    level: int


@dataclass(frozen=True)
class FontHeadingCandidate:
    text: str
    level: int


_CHAPTER_RE = re.compile(
    r"^(?:CHƯƠNG|CHƯƠNG\s+SỐ|PHẦN)\s*(?:[IVXLCDM]+|\d+)\b",
    re.IGNORECASE,
)
_NUMBERED_RE = re.compile(
    r"^(?:Điều\s+\d+|[1-9]\d*(?:\.[1-9]\d*){0,2}(?:[.)]|\s))",
    re.IGNORECASE,
)
_ROMAN_RE = re.compile(r"^[IVXLCDM]+\.", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")
_PARAGRAPH_END = (".", "!", "?", ":", ";", "…", "”", '"', ")", "]")


def _normalized_text(text: str) -> str:
    normalized = _WS_RE.sub(" ", (text or "").strip()).casefold()
    return normalized.rstrip(" ·:-")


def _matching_heading_level(
    text: str,
    font_levels: dict[str, int],
) -> int | None:
    key = _normalized_text(text)
    if key in font_levels:
        return font_levels[key]
    for candidate, level in font_levels.items():
        if len(candidate) >= 4 and (
            key.startswith(candidate)
            or candidate.startswith(key)
            or candidate in key
            or key in candidate
        ):
            return level
    return None


def read_pdf_outlines(pdf_bytes: bytes) -> list[PdfOutline]:
    """Đọc bookmark/outline cấp 1-3 từ PDF bằng PyMuPDF."""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        if pdf.is_encrypted:
            raise ValueError("PDF has a password")
        toc = pdf.get_toc(simple=True)

    return [
        PdfOutline(title=str(title).strip(), level=max(1, min(3, int(level))))
        for level, title, _page in toc
        if str(title).strip()
    ]


def _convert_layout_fallback(pdf_bytes: bytes) -> bytes:
    """Fallback an toàn khi pdf2docx không nhận diện trang/text."""
    document = Document()
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        for page in pdf:
            blocks = page.get_text("blocks")
            for block in blocks:
                text = _normalized_text(str(block[4]))
                if text:
                    document.add_paragraph(text)
            if page.number < pdf.page_count - 1:
                document.add_page_break()

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def convert_to_docx(pdf_bytes: bytes) -> bytes:
    """Convert layout PDF sang DOCX bằng pdf2docx."""
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("Dữ liệu không phải PDF")

    with tempfile.TemporaryDirectory() as temp_dir:
        pdf_path = Path(temp_dir) / "source.pdf"
        docx_path = Path(temp_dir) / "converted.docx"
        pdf_path.write_bytes(pdf_bytes)

        converter = Converter(str(pdf_path))
        try:
            converter.convert(str(docx_path), start=0, end=-1)
        except Exception as conversion_error:
            try:
                return _convert_layout_fallback(pdf_bytes)
            except Exception:
                raise RuntimeError("Không thể convert PDF sang DOCX") from conversion_error
        finally:
            if converter is not None:
                converter.close()

        if not docx_path.exists():
            raise RuntimeError("pdf2docx không tạo được file DOCX")
        return docx_path.read_bytes()


def _font_heading_candidates(pdf_bytes: bytes) -> list[FontHeadingCandidate]:
    """Suy ra candidate heading từ font-size + bold, không dùng làm fallback chính."""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        size_counts: Counter[int] = Counter()
        spans: list[tuple[str, float, bool]] = []
        for page in pdf:
            for block in page.get_text("dict").get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = _normalized_text(span.get("text", ""))
                        if not text:
                            continue
                        size = float(span.get("size", 0))
                        if size > 0:
                            size_counts[round(size * 2) / 2] += len(text)
                        font = str(span.get("font", "")).lower()
                        spans.append((text, size, "bold" in font or "black" in font))

    if not size_counts:
        return []

    normal_size = size_counts.most_common(1)[0][0]
    candidates: list[FontHeadingCandidate] = []
    for text, size, bold in spans:
        if len(text) > 120:
            continue
        is_roman = bool(_ROMAN_RE.match(text))
        is_numbered = bool(_NUMBERED_RE.match(text))
        is_chapter = bool(_CHAPTER_RE.match(text))
        is_article = bool(re.match(r"^Điều\s+\d+", text, re.IGNORECASE))
        if not (size > normal_size * 1.08 or (bold and (is_chapter or is_article or is_numbered))):
            continue

        if is_chapter:
            level = 1
        elif is_roman or re.match(r"^[1-9]\d*\.\s", text):
            level = 1
        elif re.match(r"^[1-9]\d*\.[1-9]\d*\.", text) or is_numbered:
            level = 2
        else:
            level = 1 if size >= normal_size * 1.35 else 2
        candidates.append(FontHeadingCandidate(text=text, level=level))
    return candidates


def _fallback_heading_level(text: str) -> int | None:
    stripped = text.strip()
    if _CHAPTER_RE.match(stripped):
        return 1
    if re.match(r"^Điều\s+\d+", stripped, re.IGNORECASE):
        return 2
    if re.match(r"^[1-9]\d*\.$", stripped):
        return 1
    if re.match(
        r"^[1-9]\d*\.[1-9]\d*\.[1-9]\d*(?:\.|\s)",
        stripped,
    ):
        return 3
    if re.match(r"^[1-9]\d*\.[1-9]\d*\.", stripped):
        return 2
    if re.match(r"^[A-Z]\s*[.)]\s*", stripped):
        return 3
    return None


def apply_word_styles(
    docx_bytes: bytes,
    *,
    pdf_bytes: bytes,
) -> bytes:
    """Gán Heading theo bookmark trước; regex/font fallback chỉ nếu không có bookmark."""
    document = Document(io.BytesIO(docx_bytes))
    outlines = read_pdf_outlines(pdf_bytes)

    outline_levels: dict[str, int] = {}
    for outline in outlines:
        key = _normalized_text(outline.title)
        if key:
            outline_levels[key] = outline.level

    font_candidates = _font_heading_candidates(pdf_bytes) if len(outline_levels) < 2 else []
    font_levels: dict[str, int] = {}
    for candidate in font_candidates:
        font_levels.setdefault(_normalized_text(candidate.text), candidate.level)

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        key = _normalized_text(text)

        level = outline_levels.get(key)
        if level is None and len(outline_levels) < 2:
            level = _fallback_heading_level(text)
        if level is None and len(outline_levels) < 2:
            level = _matching_heading_level(text, font_levels)
        if level is not None:
            level = max(1, min(3, level))
            paragraph.style = document.styles[f"Heading {level}"]

    headings = [
        (int(paragraph.style.name[-1]), paragraph.text)
        for paragraph in document.paragraphs
        if paragraph.style.name in ("Heading 1", "Heading 2", "Heading 3")
        and paragraph.text.strip()
    ]

    if headings:
        inject_table_of_contents(document)
    document.core_properties.title = document.core_properties.title or ""

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def inject_table_of_contents(document: Document) -> None:
    """Chèn TOC OOXML đúng cú pháp + w:dirty=true."""
    title = document.add_paragraph()
    title.style = document.styles["Title"]
    title.add_run("Mục lục")

    paragraph = document.add_paragraph()
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    begin.set(qn("w:dirty"), "true")
    run._r.append(begin)

    run = paragraph.add_run()
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = ' TOC \\o "1-3" \\h \\z \\u '
    run._r.append(instr)

    run = paragraph.add_run()
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    run._r.append(separate)
    paragraph.add_run("Nhấp chuột phải và chọn Cập nhật Mục lục.")

    run = paragraph.add_run()
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(end)

    body = document._element.body
    body.remove(title._p)
    body.remove(paragraph._p)
    body.insert(0, paragraph._p)
    body.insert(0, title._p)

    page_break = OxmlElement("w:p")
    p_pr = OxmlElement("w:pPr")
    page_break.append(p_pr)
    r = OxmlElement("w:r")
    br = OxmlElement("w:br")
    br.set(qn("w:type"), "page")
    r.append(br)
    page_break.append(r)
    body.insert(2, page_break)

    settings = document.settings.element
    update_fields = settings.find(qn("w:updateFields"))
    if update_fields is None:
        update_fields = OxmlElement("w:updateFields")
        update_fields.set(qn("w:val"), "true")
        settings.insert(0, update_fields)


def export_pdf_to_docx(pdf_bytes: bytes, title: str | None = None) -> bytes:
    """API module hóa: outline → layout conversion → styles + TOC."""
    docx_bytes = convert_to_docx(pdf_bytes)
    docx_bytes = apply_word_styles(docx_bytes, pdf_bytes=pdf_bytes)
    document = Document(io.BytesIO(docx_bytes))
    if title:
        document.core_properties.title = title
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
