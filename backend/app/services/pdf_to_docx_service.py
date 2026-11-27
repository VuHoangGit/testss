"""Export PDF sang DOCX bằng layout thực + hậu xử lý Heading/TOC.

Luồng:
1. PyMuPDF đọc outline và metadata font của PDF.
2. pdf2docx chuyển PDF thành DOCX tạm để giữ layout/bảng/font.
3. Nếu pdf2docx làm mất chữ hoa hoặc bảng, PyMuPDF dựng lại nội dung theo tọa độ.
4. python-docx gán Heading 1-3 và chèn TOC field động.
"""

from __future__ import annotations

import io
import logging
import re
import tempfile
import warnings
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

warnings.filterwarnings(
    "ignore",
    message=r"The `fitz` API is deprecated",
    category=FutureWarning,
)

import pymupdf as fitz  # noqa: E402
from docx import Document  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER  # noqa: E402
from docx.oxml import OxmlElement, parse_xml  # noqa: E402
from docx.oxml.ns import nsdecls, qn  # noqa: E402
from docx.shared import Inches, Pt, RGBColor  # noqa: E402
from docx.text.paragraph import Paragraph  # noqa: E402
from docx.text.run import Run  # noqa: E402
from pdf2docx import Converter  # noqa: E402

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PdfOutline:
    title: str
    level: int


@dataclass(frozen=True)
class FontHeadingCandidate:
    text: str
    level: int


@dataclass
class _RebuiltTableRow:
    cells: list[str]
    merged_ranges: list[tuple[int, int]]
    # Per-cell PDF spans so cell text keeps its bold/size/colour instead of being
    # flattened by assigning ``cell.text``.
    cell_spans: list[list[dict]] | None = None


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
_TOC_ENTRY_RE = re.compile(r"^(.*?)[.·…]{2,}\s*(\d+)\s*$")
_FEATURE_CODE_RE = re.compile(r"\bF\d+(?:\.\d+)?(?:\s*\+\s*F\d+(?:\.\d+)?)*\b")
_FEATURE_DEPENDENCY_RE = re.compile(
    r"Postgres(?:\s*\+\s*pgvector)?|"
    r"Gần\s+như\s+tất\s+cả|"
    r"S\d+(?:\s*\+\s*S\d+)?(?:\s*\((?:viewer|bbox)\))?",
    re.IGNORECASE,
)
_FEATURE_TABLE_HEADERS = (
    "#",
    "Sprint",
    "Feature",
    "Mục tiêu chính",
    "Phụ thuộc",
    "Trạng thái",
)
_PARAGRAPH_END = (".", "!", "?", ":", ";", "…", "”", '"', ")", "]")
_BULLET_PREFIXES = ("•", "▪", "◦", "‣", "●", "○", "–", "—", "*", "·", "-")
_CONTACT_RE = re.compile(r"[\w.+-]+@[\w-]+\.\w+|(?:\+?\d[\d\s.\-()]{7,}\d)")
# PDF text layers often emit the number of a heading as its own span ("1." + "Introduction"),
# so compare candidate and paragraph with any leading auto-number peeled off.
_LEADING_NUMBER_RE = re.compile(
    r"^(?:(?:chương|phần|chapter|part)\s*)?"
    r"(?:\d+(?:\.\d+)*|[ivxlcdm]+)"
    r"(?:[.)]|\s+)\s*",
    re.IGNORECASE,
)
# A heading never ends a sentence: treat `,` like the other terminal punctuation.
_HEADING_END = (*_PARAGRAPH_END, ",")
# Below this many promoted paragraphs the 25% sanity gate is meaningless.
_HEADING_SANITY_FLOOR = 8
_HEADING_STYLES = tuple(f"Heading {level}" for level in range(1, 7))

# PostScript names coming out of a PDF are not font families Word can resolve; untouched
# they make Word silently substitute a font, which loses "keep the original typeface".
_FONT_SUBSET_RE = re.compile(r"^[A-Z]{6}\+")
_FONT_STYLE_SUFFIX_RE = re.compile(
    r"(?:[-,]?(?:bolditalic|bold[- ]?italic|italic|oblique|bold|black|light|regular))+$",
    re.IGNORECASE,
)
_FONT_VENDOR_SUFFIX_RE = re.compile(r"(?:psmt|ps|mt)$", re.IGNORECASE)
_FONT_ALIASES = {
    "arial": "Arial",
    "arialmt": "Arial",
    "arialnarrow": "Arial Narrow",
    "helvetica": "Arial",
    "nimbussans": "Arial",
    "nimbussansl": "Arial",
    "liberationsans": "Arial",
    "vnarial": "Arial",
    "calibri": "Calibri",
    "calibrilight": "Calibri",
    "cambria": "Cambria",
    "cambriaps": "Cambria",
    "timesnewroman": "Times New Roman",
    "timesnewromanps": "Times New Roman",
    "liberationserif": "Times New Roman",
    "symbol": "Symbol",
    "wingdings": "Wingdings",
    "wingdings2": "Wingdings 2",
    "wingdings3": "Wingdings 3",
    "zapfdingbats": "ZapfDingbats",
}
_SYMBOL_FONTS = frozenset({"Symbol", "Wingdings", "Wingdings 2", "Wingdings 3", "ZapfDingbats"})


def _font_style_hints(pdf_font: str) -> tuple[bool, bool]:
    """Recover (bold, italic) from PostScript suffixes when span flags are unavailable."""
    name = (pdf_font or "").casefold()
    return "bold" in name or "black" in name, "italic" in name or "oblique" in name


def _word_font_name(pdf_font: str) -> str:
    """Map a PDF PostScript font name onto an installed Windows font family."""
    name = _FONT_SUBSET_RE.sub("", (pdf_font or "").strip())
    if not name:
        return ""
    for _ in range(3):
        stripped = _FONT_STYLE_SUFFIX_RE.sub("", name)
        stripped = _FONT_VENDOR_SUFFIX_RE.sub("", stripped)
        if stripped == name or not stripped.strip():
            break
        name = stripped.strip()
    return _FONT_ALIASES.get(re.sub(r"[^a-z0-9]", "", name.casefold()), name)


def _apply_font_name(run, name: str) -> None:
    """Set ascii/hAnsi/cs typefaces; symbol faces get an east-asian hint for glyphs."""
    if not name:
        return
    run.font.name = name
    r_fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    r_fonts.set(qn("w:cs"), name)
    if name in _SYMBOL_FONTS:
        r_fonts.set(qn("w:hint"), "eastAsia")


# ---------------------------------------------------------------------------
# Numbering / lists
#
# pdf2docx never emits `w:numPr` (its list detection is hard-disabled:
# `pdf2docx/text/Lines.py:84` reads `if 0 and is_list_item(...)`), so every bullet
# arrives as a literal glyph in the text. The post-pass below turns those glyphs into
# real Word list numbering.
_PUA_GLYPH_MAP = {
    "": "•",  # Symbol bullet
    "": "▪",  # Wingdings small square
    "": "➢",  # Wingdings arrow
    "": "✓",  # Wingdings check mark
}
_BULLET_GLYPH_RE = re.compile(r"^[•▪◦‣●○]\s?")
_DASH_BULLET_RE = re.compile(r"^[-–—*]\s")
_LIST_MARKER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("roman", re.compile(r"^[ivxlcdm]{1,5}[.)]\s", re.IGNORECASE)),
    ("letter", re.compile(r"^[a-zđ][.)]\s", re.IGNORECASE)),
    ("decimal", re.compile(r"^\d{1,2}[.)]\s")),
)
_NUM_FMT = {
    "bullet": "bullet",
    "decimal": "decimal",
    "letter": "lowerLetter",
    "roman": "lowerRoman",
}
# 36pt per nesting level, expressed in twips (1pt = 20twips).
_TWIPS_PER_LEVEL = 720
# CT_PPr child sequence (ECMA-376 §17.3.1.26). Word tolerates some reordering but not
# numPr placed before widowControl, so insert by rank instead of at index 0.
_PPR_ORDER = (
    "w:pStyle", "w:keepNext", "w:keepLines", "w:pageBreakBefore", "w:framePr",
    "w:widowControl", "w:numPr", "w:suppressLineNumbers", "w:pBdr", "w:shd", "w:tabs",
    "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap", "w:overflowPunct",
    "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi", "w:adjustRightInd",
    "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing", "w:mirrorIndents",
    "w:suppressOverlap", "w:jc", "w:textDirection", "w:textAlignment",
    "w:textboxTightWrap", "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr",
    "w:sectPr", "w:pPrChange",
)


def _insert_ppr_child(p_pr, child, tag: str) -> None:
    """Insert `child` right after the last property that ranks before it in CT_PPr."""
    rank = _PPR_ORDER.index(tag)
    previous = None
    for existing in p_pr:
        existing_tag = f"w:{existing.tag.split('}')[-1]}"
        if existing_tag in _PPR_ORDER and _PPR_ORDER.index(existing_tag) < rank:
            previous = existing
    if previous is None:
        p_pr.insert(0, child)
    else:
        previous.addnext(child)


def _list_marker(text: str) -> tuple[int, str] | None:
    """Return (marker length in characters, list kind) for a paragraph starting a list item."""
    if not text:
        return None
    if text[0] in _PUA_GLYPH_MAP:
        return 1, "bullet"
    match = _BULLET_GLYPH_RE.match(text) or _DASH_BULLET_RE.match(text)
    if match:
        return len(match.group(0)), "bullet"
    for kind, pattern in _LIST_MARKER_PATTERNS:
        match = pattern.match(text)
        if match:
            return len(match.group(0)), kind
    return None


def _strip_leading_text(paragraph, length: int) -> None:
    """Remove the first `length` characters of a paragraph, marker first, then stray blanks."""
    remaining = length
    for run in paragraph.runs:
        if remaining <= 0:
            break
        text = run.text
        if not text:
            continue
        take = min(remaining, len(text))
        run.text = text[take:]
        remaining -= take
    for run in paragraph.runs:
        text = run.text
        if not text:
            continue
        trimmed = text.lstrip("\t  ")
        if trimmed != text:
            run.text = trimmed
        break


def _abstract_num_xml(abstract_id: int, kind: str) -> str:
    """One 9-level abstractNum in schema order (start, numFmt, lvlText, lvlJc, pPr, rPr)."""
    levels: list[str] = []
    for level in range(9):
        left = _TWIPS_PER_LEVEL * (level + 1)
        if kind == "bullet":
            # Real Unicode bullets, so no rFonts override: forcing Symbol on U+2022
            # (a glyph Symbol does not contain) renders the wrong character.
            lvl_text = ("•", "◦", "▪")[level % 3]
            run_props = ""
        else:
            lvl_text = (f"%{level + 1}.", f"%{level + 1})")[level % 2]
            run_props = ""
        levels.append(
            f'<w:lvl w:ilvl="{level}"><w:start w:val="1"/>'
            f'<w:numFmt w:val="{_NUM_FMT[kind]}"/>'
            f'<w:lvlText w:val="{lvl_text}"/><w:lvlJc w:val="left"/>'
            f'<w:pPr><w:ind w:left="{left}" w:hanging="360"/></w:pPr>{run_props}</w:lvl>'
        )
    return (
        f'<w:abstractNum {nsdecls("w")} w:abstractNumId="{abstract_id}">'
        '<w:multiLevelType w:val="hybridMultilevel"/>' + "".join(levels) + "</w:abstractNum>"
    )


def _ensure_list_numbering(document: Document) -> dict[str, int]:
    """Add bullet/decimal/letter/roman abstractNum + num pairs, returning numId per kind."""
    numbering = document.part.numbering_part.element
    abstract_elements = numbering.findall(qn("w:abstractNum"))
    abstract_ids = [int(element.get(qn("w:abstractNumId"))) for element in abstract_elements]
    num_ids = [int(e.get(qn("w:numId"))) for e in numbering.findall(qn("w:num"))]
    next_abstract = max(abstract_ids, default=-1) + 1
    next_num = max(num_ids, default=0) + 1

    kind_num_ids: dict[str, int] = {}
    for kind in _NUM_FMT:
        abstract = parse_xml(_abstract_num_xml(next_abstract, kind))
        existing_abstract = numbering.findall(qn("w:abstractNum"))
        if existing_abstract:
            existing_abstract[-1].addnext(abstract)
        else:
            numbering.insert(0, abstract)
        numbering.append(
            parse_xml(
                f'<w:num {nsdecls("w")} w:numId="{next_num}">'
                f'<w:abstractNumId w:val="{next_abstract}"/></w:num>'
            )
        )
        kind_num_ids[kind] = next_num
        next_abstract += 1
        next_num += 1
    return kind_num_ids


def _set_list_numbering(paragraph, *, num_id: int, level: int) -> None:
    """Attach explicit `w:numPr`; paragraph-level numbering wins over any style default."""
    p_pr = paragraph._p.get_or_add_pPr()
    num_pr = p_pr.find(qn("w:numPr"))
    if num_pr is None:
        num_pr = OxmlElement("w:numPr")
        _insert_ppr_child(p_pr, num_pr, "w:numPr")
    for child in list(num_pr):
        num_pr.remove(child)
    ilvl = OxmlElement("w:ilvl")
    ilvl.set(qn("w:val"), str(level))
    num_pr.append(ilvl)
    num_id_element = OxmlElement("w:numId")
    num_id_element.set(qn("w:val"), str(num_id))
    num_pr.append(num_id_element)


def _list_level(paragraph) -> int:
    """Nesting level from the paragraph indent; ~36pt (720twips) per level."""
    p_pr = paragraph._p.pPr
    indentation = p_pr.find(qn("w:ind")) if p_pr is not None else None
    left = 0
    if indentation is not None:
        raw = indentation.get(qn("w:left"))
        if raw and raw.lstrip("-").isdigit():
            left = max(0, int(raw))
    return min(8, left // _TWIPS_PER_LEVEL)


def _apply_list_numbering(document: Document) -> int:
    """Convert leading bullet/number glyphs into real Word numbering.

    Must run *after* heading assignment: headings that carry a typed number
    ("3.1.1 Activities") would otherwise be re-numbered and double up.
    """
    kind_num_ids = _ensure_list_numbering(document)
    converted = 0
    for paragraph in _iter_all_paragraphs(document):
        if paragraph.style.name.startswith("Heading") or paragraph.style.name == "Title":
            continue
        text = paragraph.text
        if not text.strip():
            continue
        marker = _list_marker(text)
        if marker is None:
            continue
        length, kind = marker
        level = _list_level(paragraph)
        _strip_leading_text(paragraph, length)
        if not paragraph.text.strip():
            continue
        _set_list_numbering(paragraph, num_id=kind_num_ids[kind], level=level)
        converted += 1
    return converted


def _normalized_text(text: str) -> str:
    normalized = _WS_RE.sub(" ", (text or "").strip()).casefold()
    return normalized.rstrip(" ·:-")


def _looks_like_heading(text: str) -> bool:
    """Reject bullets, contact lines and sentence fragments before ranking as heading."""
    stripped = (text or "").strip()
    if not stripped:
        return False
    if stripped.startswith(_BULLET_PREFIXES):
        return False
    if _CONTACT_RE.search(stripped):
        return False
    return not stripped.endswith(_HEADING_END)


def _matching_heading_level(
    text: str,
    font_levels: dict[str, int],
) -> int | None:
    """Prefix-only match against font-derived candidates.

    Substring matching in either direction used to promote any body paragraph that
    merely *contained* a candidate string, which is how prose ended up as Heading 1.
    """
    key = _normalized_text(text)
    if key in font_levels:
        return font_levels[key]
    if not _looks_like_heading(key):
        return None
    bare_key = _LEADING_NUMBER_RE.sub("", key)
    for candidate, level in font_levels.items():
        if len(candidate) >= 4 and (key.startswith(candidate) or bare_key.startswith(candidate)):
            return level
        bare_candidate = _LEADING_NUMBER_RE.sub("", candidate)
        if len(bare_candidate) >= 4 and bare_key.startswith(bare_candidate):
            return level
    return None


def read_pdf_outlines(pdf_bytes: bytes) -> list[PdfOutline]:
    """Đọc bookmark/outline cấp 1-3 từ PDF bằng PyMuPDF."""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        if pdf.is_encrypted:
            raise ValueError("PDF has a password")
        toc = pdf.get_toc(simple=True)

    return [
        PdfOutline(title=str(title).strip(), level=max(1, min(6, int(level))))
        for level, title, _page in toc
        if str(title).strip()
    ]


def _convert_layout_fallback(pdf_bytes: bytes) -> bytes:
    """Rebuild text and detected tables from PDF geometry when conversion loses content."""
    document = Document()
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        for page in pdf:
            table_finder = page.find_tables()
            tables = sorted(table_finder.tables, key=lambda table: table.bbox[1])
            events: list[tuple[float, str, object]] = [
                (table.bbox[1], "table", table) for table in tables
            ]
            pdf_lines = _read_pdf_lines(page)
            table_rows = {id(table): _logical_table_rows(table, pdf_lines) for table in tables}
            feature_rows = next(
                (
                    rows
                    for table in tables
                    if (rows := _rebuild_feature_matrix_rows(table_rows[id(table)]))
                ),
                None,
            )
            toc_lines = [
                line
                for line in pdf_lines
                if _TOC_ENTRY_RE.match(_repair_spacing(_line_text(line["spans"])))
            ]
            if feature_rows and toc_lines:
                events.append(
                    (
                        min(line["bbox"][1] for line in toc_lines),
                        "feature_toc",
                        feature_rows,
                    )
                )

            for info in page.get_image_info(xrefs=True):
                bbox = info.get("bbox")
                xref = int(info.get("xref") or 0)
                if not bbox or not xref:
                    continue
                if _line_is_inside_table(tuple(bbox), tables):
                    continue
                events.append((float(bbox[1]), "image", (bbox, xref)))

            for line in pdf_lines:
                spans = sorted(line["spans"], key=lambda span: span["bbox"][0])
                text = _line_text(spans)
                if not text or _line_is_inside_table(line["bbox"], tables):
                    continue
                if feature_rows and _TOC_ENTRY_RE.match(_repair_spacing(text)):
                    continue
                events.append((line["bbox"][1], "line", (text, spans)))

            for _y, kind, value in sorted(events, key=lambda event: event[0]):
                if kind == "table":
                    source_table = value
                    feature_table_rows = _rebuild_feature_matrix_rows(table_rows[id(source_table)])
                    source_rows = feature_table_rows or table_rows[id(source_table)]
                    if not source_rows:
                        continue
                    column_count = (
                        len(_FEATURE_TABLE_HEADERS)
                        if feature_table_rows
                        else source_table.col_count
                    )
                    table = document.add_table(
                        rows=len(source_rows),
                        cols=column_count,
                    )
                    table.style = "Table Grid"
                    shade = _header_shading(page, source_table)
                    for row_index, row in enumerate(source_rows):
                        if feature_table_rows:
                            for column_index, text in enumerate(row):
                                _fill_table_cell(table.cell(row_index, column_index), text, [])
                            continue
                        for start, end in row.merged_ranges:
                            table.cell(row_index, start).merge(table.cell(row_index, end))
                        merged_columns = {
                            column
                            for start, end in row.merged_ranges
                            for column in range(start + 1, end + 1)
                        }
                        for column_index, text in enumerate(row.cells):
                            if column_index in merged_columns:
                                continue
                            cell_spans = (row.cell_spans or [])[column_index:column_index + 1]
                            _fill_table_cell(
                                table.cell(row_index, column_index),
                                text,
                                cell_spans[0] if cell_spans else [],
                            )
                    if shade and not feature_table_rows:
                        for cell in table.rows[0].cells:
                            _apply_cell_shading(cell, shade)
                    _apply_table_geometry(table, source_table)
                elif kind == "image":
                    bbox, xref = value
                    image_bytes = _extract_pdf_image(pdf, xref)
                    if image_bytes:
                        width = Pt(max(1.0, float(bbox[2]) - float(bbox[0])))
                        document.add_paragraph().add_run().add_picture(
                            io.BytesIO(image_bytes), width=width
                        )
                elif kind == "feature_toc":
                    for row in value[1:]:
                        paragraph = document.add_paragraph()
                        paragraph.paragraph_format.tab_stops.add_tab_stop(
                            Inches(6.5),
                            WD_TAB_ALIGNMENT.RIGHT,
                            WD_TAB_LEADER.DOTS,
                        )
                        _add_pdf_spans(
                            paragraph,
                            [],
                            text_override=f"{row[0]} {row[1]}\t{page.number + 1}",
                        )
                else:
                    text, spans = value
                    text = _repair_spacing(text)
                    paragraph = document.add_paragraph()
                    toc_entry = _TOC_ENTRY_RE.match(text)
                    if toc_entry:
                        if _is_pdf_artifact(toc_entry[1]):
                            document._element.body.remove(paragraph._p)
                            continue
                        paragraph.paragraph_format.tab_stops.add_tab_stop(
                            Inches(6.5),
                            WD_TAB_ALIGNMENT.RIGHT,
                            WD_TAB_LEADER.DOTS,
                        )
                        toc_text = f"{toc_entry[1]}\t{toc_entry[2]}"
                        _add_pdf_spans(paragraph, spans, text_override=toc_text)
                    else:
                        _add_pdf_spans(paragraph, spans)
            if page.number < pdf.page_count - 1:
                document.add_page_break()

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _fill_table_cell(cell, text: str, spans: list[dict]) -> None:
    """Write cell content as formatted runs.

    ``cell.text = ...`` deletes the existing run and inserts one unformatted run, which
    is how table cells lost every bold/size/colour from the PDF.
    """
    paragraph = cell.paragraphs[0]
    for run in list(paragraph.runs):
        run._element.getparent().remove(run._element)
    if spans:
        _add_pdf_spans(paragraph, spans)
    if not paragraph.runs:
        paragraph.add_run(text)


def _extract_pdf_image(pdf, xref: int) -> bytes | None:
    """Raw bytes of an embedded image, or None when the xref is not a plain image."""
    try:
        info = pdf.extract_image(xref)
    except Exception:  # noqa: BLE001 - malformed xref must not abort the whole export
        return None
    image = (info or {}).get("image")
    return image if isinstance(image, (bytes, bytearray)) else None


def _header_shading(page, source_table) -> str | None:
    """Fill colour behind the header row, read from the page's filled rectangles."""
    header = getattr(source_table, "header", None)
    cells = list(header.cells) if header is not None and header.cells else []
    rect = next((cell for cell in cells if cell is not None), None)
    if rect is None:
        return None
    for drawing in page.get_drawings():
        fill = drawing.get("fill")
        area = drawing.get("rect")
        if not fill or area is None:
            continue
        if (
            area.x0 <= rect[0] + 1
            and area.y0 <= rect[1] + 1
            and area.x1 >= rect[2] - 1
            and area.y1 >= rect[3] - 1
        ):
            return "".join(f"{int(round(channel * 255)):02X}" for channel in fill[:3])
    return None


def _apply_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    for existing in tc_pr.findall(qn("w:shd")):
        tc_pr.remove(existing)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def _apply_table_geometry(table, source_table) -> None:
    """Column widths proportional to the header cell bboxes.

    Word honours a column width only when both ``w:gridCol`` and the individual
    ``w:tcW`` values agree, so set both.
    """
    header = getattr(source_table, "header", None)
    rects = list(header.cells) if header is not None and header.cells else []
    if not rects:
        source_rows = list(source_table.rows)
        rects = list(source_rows[0].cells) if source_rows else []
    widths = [
        max(0.0, float(rect[2]) - float(rect[0])) if rect is not None else 0.0
        for rect in rects
    ]
    if not widths or sum(widths) <= 0:
        return
    for index, width in enumerate(widths):
        if width <= 0 or index >= len(table.columns):
            continue
        table.columns[index].width = Pt(width)
        for row in table.rows:
            try:
                row.cells[index].width = Pt(width)
            except IndexError:
                continue


def _logical_table_rows(source_table, lines: list[dict]) -> list[_RebuiltTableRow]:
    rows: list[_RebuiltTableRow] = []
    current_row: _RebuiltTableRow | None = None

    for source_row in source_table.rows:
        cell_rects = list(source_row.cells)
        values = [
            _text_in_rect(lines, cell_rect) if cell_rect is not None else ""
            for cell_rect in cell_rects
        ]
        values = [_repair_spacing(_clean_pdf_text(value)) for value in values]
        cell_spans = [
            _spans_in_rect(lines, cell_rect) if cell_rect is not None else []
            for cell_rect in cell_rects
        ]
        first_cell = values[0].strip() if values else ""
        merged_ranges = _row_merge_ranges(cell_rects)

        if not any(values):
            continue
        if first_cell == "#" or first_cell.isdigit():
            rows.append(_RebuiltTableRow(values, merged_ranges, cell_spans))
            current_row = rows[-1]
        elif _is_pdf_artifact(first_cell):
            if current_row:
                _append_table_row_content(current_row, values[1:], cell_spans[1:])
            elif any(values[1:]):
                rows.append(_RebuiltTableRow(values, merged_ranges, cell_spans))
                current_row = rows[-1]
        elif current_row and _is_continuation_row(first_cell, current_row):
            _append_overflow_row(current_row, values, cell_spans)
        else:
            # Bảng không có cột khóa "#"/số: giữ nguyên dòng thay vì bỏ mất nội dung.
            rows.append(_RebuiltTableRow(values, merged_ranges, cell_spans))
            current_row = rows[-1]

    return rows


def _spans_in_rect(lines: list[dict], rect: tuple) -> list[dict]:
    """Line spans whose centre lies inside `rect`, with the in-cell text substituted."""
    x0, y0, x1, y1 = rect
    selected: list[dict] = []
    for line in lines:
        for span in line["spans"]:
            characters = [
                character
                for character in span.get("chars", [])
                if x0 - 0.5 <= (character["bbox"][0] + character["bbox"][2]) / 2 <= x1 + 0.5
                and y0 - 0.5 <= (character["bbox"][1] + character["bbox"][3]) / 2 <= y1 + 0.5
            ]
            text = _text_from_positioned_chars(
                [(character, float(span.get("size", 0))) for character in characters]
            )
            if text:
                selected.append({**span, "text": text})
    return selected


_ROW_CONTINUATION_ENDS = ("+", "&", ",", "—", "-", "/", "(", "→", "=")


def _is_continuation_row(first_cell: str, current_row: _RebuiltTableRow) -> bool:
    """Dòng grid nối tiếp logical row trước: ô đầu bắt đầu chữ thường (lớp chữ lỗi
    như "pgvector0%") hoặc ô cuối dòng trước treo dấu nối ("Postgres +")."""
    if first_cell[:1].islower():
        return True
    last_content = next(
        (cell for cell in reversed(current_row.cells) if cell.strip()),
        "",
    )
    return bool(last_content) and last_content.rstrip().endswith(_ROW_CONTINUATION_ENDS)


def _rebuild_feature_matrix_rows(
    rows: list[_RebuiltTableRow],
) -> list[list[str]]:
    """Split the sprint/feature matrix of one specific report into its 6 real columns.

    Deliberately narrow: it requires the exact header set in `_FEATURE_TABLE_HEADERS`
    and an "F<number>" feature code, and returns `[]` for anything else. Kept as-is
    because `test_feature_matrix_rebuild_splits_columns_and_extracts_toc_data` and the
    `feature_toc` event depend on it; it must not be reused as a generic table parser.
    """
    if not rows:
        return []
    header_text = _normalized_text(" ".join(rows[0].cells))
    if not all(_normalized_text(header) in header_text for header in _FEATURE_TABLE_HEADERS):
        return []

    rebuilt_rows = [list(_FEATURE_TABLE_HEADERS)]
    for row in rows[1:]:
        if not row.cells[0].strip().isdigit():
            continue
        content = _repair_spacing(" ".join(cell for cell in row.cells[1:] if cell))
        status_matches = list(re.finditer(r"~?\d+%", content))
        status = status_matches[-1][0] if status_matches else ""
        content = re.sub(r"~?\d+%", "", content)

        dependencies = list(
            dict.fromkeys(match.group(0) for match in _FEATURE_DEPENDENCY_RE.finditer(content))
        )
        content = _FEATURE_DEPENDENCY_RE.sub("", content)
        feature_match = _FEATURE_CODE_RE.search(content)
        if feature_match is None:
            return []

        sprint = content[: feature_match.start()].strip()
        objective = content[feature_match.end() :].strip()
        rebuilt_rows.append(
            [
                row.cells[0].strip(),
                _WS_RE.sub(" ", sprint),
                feature_match.group(0),
                _WS_RE.sub(" ", objective).strip(" —–"),
                "; ".join(dependencies),
                status,
            ]
        )
    return rebuilt_rows if len(rebuilt_rows) > 1 else []


def _row_merge_ranges(cells: list[tuple | None]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for index, cell in enumerate(cells):
        if cell is None:
            continue
        end = index
        for next_index in range(index + 1, len(cells)):
            if cells[next_index] is not None:
                break
            end = next_index
        if end > index:
            ranges.append((index, end))
    return ranges


def _append_table_row_content(
    row: _RebuiltTableRow,
    values: list[str],
    spans: list[list[dict]] | None = None,
) -> None:
    for index, value in enumerate(values, start=1):
        if value and index < len(row.cells):
            row.cells[index] = f"{row.cells[index]} {value}".strip()
            if spans and row.cell_spans is not None and index < len(row.cell_spans):
                row.cell_spans[index] = list(row.cell_spans[index]) + list(spans[index - 1])


def _append_overflow_row(
    row: _RebuiltTableRow,
    values: list[str],
    spans: list[list[dict]] | None = None,
) -> None:
    """Gộp dòng tràn cột vào logical row trước đó, ưu tiên đúng cột khi có thể."""
    target_index = max(
        (index for index, value in enumerate(row.cells) if value),
        default=1,
    )
    for index, value in enumerate(values):
        if not value:
            continue
        if index < len(row.cells) and index > 0 and not row.cells[index].strip():
            row.cells[index] = value.strip()
            if spans and row.cell_spans is not None and index < len(row.cell_spans):
                row.cell_spans[index] = list(spans[index])
        else:
            row.cells[target_index] = f"{row.cells[target_index]} {value}".strip()
            if spans and row.cell_spans is not None and target_index < len(row.cell_spans):
                row.cell_spans[target_index] = (
                    list(row.cell_spans[target_index]) + list(spans[index])
                )
    # Giữ heuristic phần trăm cũ cho file lớp chữ lỗi (vd "pgvector0%").
    percent = re.search(r"~?(\d+%)$", row.cells[target_index])
    if percent:
        status = percent[1]
        details = row.cells[target_index][: percent.start()].strip()
        row.cells[target_index] = details
        if row.cells:
            last = len(row.cells) - 1
            last_cell = row.cells[last].strip()
            row.cells[last] = f"{last_cell} {status}".strip() if last_cell else status


def _clean_pdf_text(text: str) -> str:
    cleaned = re.sub(r"[\ufffd\ud800-\udfff]", "", text)
    cleaned = re.sub(r"(?<=\d)\s+s(?=[A-Z]{2}\b)", " ", cleaned)
    return re.sub(r"^s(?=[A-Z]{2}\b)", "", cleaned).strip()


def _is_pdf_artifact(text: str) -> bool:
    return text.strip() in {"", "s", "\ufffd"}


# Workarounds for one specific source document, not general logic: the text layer of
# the sprint report PDF drops the space inside these Vietnamese words.
_DOC_SPECIFIC_REPAIRS = {
    "Phụthuộc": "Phụ thuộc",
    "Trạngthái": "Trạng thái",
}


def _repair_spacing(text: str) -> str:
    repaired: list[str] = []
    for character in text:
        if repaired and (
            (repaired[-1].islower() and character.isupper())
            or (repaired[-1].islower() and character.isdigit())
            or (repaired[-1].isdigit() and character.isupper())
        ):
            repaired.append(" ")
        repaired.append(character)
    repaired_text = "".join(repaired)
    for broken, fixed in _DOC_SPECIFIC_REPAIRS.items():
        repaired_text = repaired_text.replace(broken, fixed)
    return repaired_text


def _line_text(spans: list[dict]) -> str:
    parts: list[str] = []
    previous_span: dict | None = None
    for span in spans:
        text = _clean_pdf_text(str(span.get("text", "")))
        if not text:
            continue
        if previous_span is not None:
            gap = span["bbox"][0] - previous_span["bbox"][2]
            if gap > max(1.0, float(span.get("size", 0)) * 0.15):
                parts.append(" ")
        parts.append(text)
        previous_span = span
    return "".join(parts).strip()


def _line_is_inside_table(line_bbox: tuple, tables: list) -> bool:
    x0, y0, x1, y1 = line_bbox
    center_x = (x0 + x1) / 2
    center_y = (y0 + y1) / 2
    return any(
        table.bbox[0] <= center_x <= table.bbox[2] and table.bbox[1] <= center_y <= table.bbox[3]
        for table in tables
    )


def _text_in_rect(lines: list[dict], rect: tuple) -> str:
    x0, y0, x1, y1 = rect
    text_lines: list[str] = []
    for line in lines:
        selected = [
            (character, float(span.get("size", 0)))
            for span in line["spans"]
            for character in span.get("chars", [])
            if x0 - 0.5 <= (character["bbox"][0] + character["bbox"][2]) / 2 <= x1 + 0.5
            and y0 - 0.5 <= (character["bbox"][1] + character["bbox"][3]) / 2 <= y1 + 0.5
        ]
        text = _text_from_positioned_chars(selected)
        if text:
            text_lines.append(text)
    return "\n".join(text_lines)


def _read_pdf_lines(page) -> list[dict]:
    lines: list[dict] = []
    for block in page.get_text("rawdict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = []
            for span in line.get("spans", []):
                text = _text_from_positioned_chars(
                    [(character, float(span.get("size", 0))) for character in span.get("chars", [])]
                )
                if text:
                    spans.append({**span, "text": text})
            if spans:
                lines.append({"bbox": line["bbox"], "spans": spans})
    return sorted(lines, key=lambda line: (line["bbox"][1], line["bbox"][0]))


def _text_from_positioned_chars(characters: list[tuple[dict, float]]) -> str:
    parts: list[str] = []
    previous_character: dict | None = None
    for character, font_size in sorted(
        characters,
        key=lambda item: item[0]["bbox"][0],
    ):
        text = str(character.get("c", ""))
        if not text:
            continue
        if previous_character is not None and text != " ":
            gap = character["origin"][0] - previous_character["bbox"][2]
            if gap > max(1.0, font_size * 0.2) and parts[-1] != " ":
                parts.append(" ")
        parts.append(text)
        previous_character = character
    return _clean_pdf_text("".join(parts)).strip()


def _add_pdf_spans(paragraph, spans: list[dict], *, text_override: str | None = None) -> None:
    if text_override is not None:
        run = paragraph.add_run(text_override)
        if spans:
            _format_pdf_run(run, spans[0])
        return

    previous_span: dict | None = None
    for span in spans:
        text = _repair_spacing(_clean_pdf_text(str(span.get("text", ""))))
        if not text:
            continue
        if previous_span is not None:
            gap = span["bbox"][0] - previous_span["bbox"][2]
            if gap > max(1.0, float(span.get("size", 0)) * 0.15):
                paragraph.add_run(" ")
        run = paragraph.add_run(text)
        _format_pdf_run(run, span)
        previous_span = span


def _format_pdf_run(run, span: dict) -> None:
    font = run.font
    pdf_font = str(span.get("font", ""))
    _apply_font_name(run, _word_font_name(pdf_font))
    font.size = Pt(float(span["size"])) if span.get("size") else None
    flags = int(span.get("flags", 0))
    name_bold, name_italic = _font_style_hints(pdf_font)
    font.italic = bool(flags & 2) or name_italic
    font.bold = bool(flags & 16) or name_bold
    color = span.get("color")
    if isinstance(color, int):
        # PyMuPDF packs alpha in the high byte; keep the low 24 bits only.
        red, green, blue = ((color & 0xFFFFFF) >> 16) & 255, ((color & 0xFFFFFF) >> 8) & 255, (
            color & 0xFFFFFF
        ) & 255
        font.color.rgb = RGBColor(red, green, blue)
    # Underline is not reconstructed: PyMuPDF exposes it only as separate line drawings,
    # and matching those to individual spans is unreliable. Documented, not silently lost.


def _normalize_run_fonts(document: Document) -> int:
    """Rewrite PostScript font names on every run, whatever produced the DOCX.

    pdf2docx writes its own typeface names, so fixing only the PyMuPDF fallback path
    would leave the common path (pdf2docx) with unresolvable fonts.
    """
    changed = 0
    for paragraph in _iter_all_paragraphs(document):
        for element in paragraph._p.iter(qn("w:r")):
            run = Run(element, paragraph)
            current = run.font.name
            if not current:
                continue
            mapped = _word_font_name(current)
            if mapped and mapped != current:
                _apply_font_name(run, mapped)
                changed += 1
    return changed


def _needs_layout_fallback(pdf_bytes: bytes, docx_bytes: bytes) -> bool:
    converted = Document(io.BytesIO(docx_bytes))
    converted_text = "\n".join(
        [paragraph.text for paragraph in converted.paragraphs]
        + [cell.text for table in converted.tables for row in table.rows for cell in row.cells]
    )
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        source_text = "\n".join(page.get_text() for page in pdf)
        pdf_table_count = sum(len(page.find_tables().tables) for page in pdf)

    if source_text.strip() and not converted_text.strip():
        return True
    source_has_uppercase = any(character.isupper() for character in source_text)
    converted_has_uppercase = any(character.isupper() for character in converted_text)
    if source_has_uppercase and not converted_has_uppercase:
        return True
    return pdf_table_count > len(converted.tables)


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
            except Exception as fallback_error:
                fallback_error.add_note(f"pdf2docx conversion also failed: {conversion_error}")
                raise RuntimeError("Không thể convert PDF sang DOCX") from fallback_error
        finally:
            if converter is not None:
                converter.close()

        if not docx_path.exists():
            raise RuntimeError("pdf2docx không tạo được file DOCX")
        docx_bytes = docx_path.read_bytes()
        if _needs_layout_fallback(pdf_bytes, docx_bytes):
            return _convert_layout_fallback(pdf_bytes)
        return docx_bytes


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

    body_size = size_counts.most_common(1)[0][0]
    candidates: list[FontHeadingCandidate] = []
    for text, size, bold in spans:
        if len(text) > 120 or not _looks_like_heading(text):
            continue
        is_roman = bool(_ROMAN_RE.match(text))
        is_numbered = bool(_NUMBERED_RE.match(text))
        is_chapter = bool(_CHAPTER_RE.match(text))
        is_article = bool(re.match(r"^Điều\s+\d+", text, re.IGNORECASE))
        if not (size > body_size * 1.08 or (bold and (is_chapter or is_article or is_numbered))):
            continue

        if is_chapter:
            level = 1
        elif is_roman or re.match(r"^[1-9]\d*\.\s", text):
            level = 1
        elif re.match(r"^[1-9]\d*\.[1-9]\d*\.", text) or is_numbered:
            level = 2
        else:
            level = 1 if size >= body_size * 1.35 else 2
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


def _iter_all_paragraphs(document: Document) -> list[Paragraph]:
    """Paragraphs in document order, including table cells, nested tables and SDTs.

    ``Document.paragraphs`` only returns body-level paragraphs. pdf2docx turns most
    of a layout PDF into tables, so the heading pass used to be blind to the bulk of
    the document.
    """
    body = document.element.body
    return [Paragraph(element, document) for element in body.iter(qn("w:p"))]


def apply_word_styles(
    docx_bytes: bytes,
    *,
    pdf_bytes: bytes,
) -> bytes:
    """Gán Heading theo bookmark trước; regex/font fallback chỉ nếu không có bookmark."""
    document = Document(io.BytesIO(docx_bytes))
    outlines = read_pdf_outlines(pdf_bytes)
    logger.info("Renamed %d PostScript font runs", _normalize_run_fonts(document))

    outline_levels: dict[str, int] = {}
    for outline in outlines:
        key = _normalized_text(outline.title)
        if key:
            outline_levels[key] = outline.level

    font_candidates = _font_heading_candidates(pdf_bytes) if len(outline_levels) < 2 else []
    font_levels: dict[str, int] = {}
    for candidate in font_candidates:
        font_levels.setdefault(_normalized_text(candidate.text), candidate.level)

    paragraphs = _iter_all_paragraphs(document)
    logger.info("Heading pass considering %d paragraphs (incl. table cells)", len(paragraphs))
    assigned: list[tuple[object, str]] = []
    for paragraph in paragraphs:
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
            level = max(1, min(6, level))
            assigned.append((paragraph, paragraph.style.name))
            paragraph.style = document.styles[f"Heading {level}"]

    # A real document never promotes a quarter of its paragraphs to headings; when it
    # does, the detection failed and a garbage TOC is worse than no TOC at all. The
    # absolute floor keeps short documents (and unit-test fixtures) out of the rule.
    if len(assigned) > max(_HEADING_SANITY_FLOOR, len(paragraphs) * 0.25):
        logger.warning(
            "Heading detection rejected: %d/%d paragraphs promoted (>25%%)",
            len(assigned),
            len(paragraphs),
        )
        for paragraph, original_style in assigned:
            paragraph.style = document.styles[original_style]
        assigned.clear()

    converted_lists = _apply_list_numbering(document)
    logger.info("Converted %d bullet/number glyphs into real lists", converted_lists)

    headings = [
        (int(paragraph.style.name[-1]), paragraph.text)
        for paragraph in paragraphs
        if paragraph.style.name in _HEADING_STYLES and paragraph.text.strip()
    ]

    if headings:
        inject_table_of_contents(document, pdf_bytes=pdf_bytes)

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _append_field_char(paragraph, field_type: str, *, dirty: bool = False) -> None:
    run = paragraph.add_run()
    fld_char = OxmlElement("w:fldChar")
    fld_char.set(qn("w:fldCharType"), field_type)
    if dirty:
        fld_char.set(qn("w:dirty"), "true")
    run._r.append(fld_char)


def _append_instr_text(paragraph, instruction: str) -> None:
    run = paragraph.add_run()
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    run._r.append(instr)


_TOC_INSTRUCTION = ' TOC \\o "1-6" \\h \\z \\u '


def _heading_page_numbers(
    pdf_bytes: bytes | None,
    headings: list[tuple[int, str]],
) -> list[int]:
    """Best-effort starting page per heading, used as the pre-populated PAGEREF result."""
    if not pdf_bytes:
        return list(range(1, len(headings) + 1))
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
            pages = [_WS_RE.sub(" ", page.get_text()).casefold() for page in pdf]
    except Exception:  # noqa: BLE001 - page numbers are cosmetic; never fail the export
        return list(range(1, len(headings) + 1))

    numbers: list[int] = []
    cursor = 0
    for _level, text in headings:
        needle = _WS_RE.sub(" ", text).casefold()[:60]
        found = None
        if needle:
            for index in range(cursor, len(pages)):
                if needle in pages[index]:
                    found = index
                    break
        if found is None:
            numbers.append(numbers[-1] if numbers else 1)
        else:
            cursor = found
            numbers.append(found + 1)
    return numbers


def _toc_anchor(body, toc_position: str) -> int:
    """Body index where the TOC block starts; `after_first_page` skips cover + TOC target."""
    if toc_position == "after_first_page":
        for index, child in enumerate(body):
            if child.tag != qn("w:p"):
                continue
            breaks = child.findall(".//" + qn("w:br"))
            if any(item.get(qn("w:type")) == "page" for item in breaks):
                return index + 1
    return 0


def _add_page_number_footer(document: Document) -> None:
    """Add a PAGE field so TOC page numbers refer to something real."""
    for index, section in enumerate(document.sections):
        if index > 0 and section.footer.is_linked_to_previous:
            # Inherits the PAGE field from the previous section.
            continue
        footer = section.footer
        paragraph = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if paragraph._p.findall(".//" + qn("w:fldSimple")):
            continue
        simple = OxmlElement("w:fldSimple")
        simple.set(qn("w:instr"), " PAGE ")
        inner_run = OxmlElement("w:r")
        placeholder = OxmlElement("w:t")
        placeholder.text = "1"
        inner_run.append(placeholder)
        simple.append(inner_run)
        paragraph._p.append(simple)


def inject_table_of_contents(
    document: Document,
    *,
    toc_position: Literal["start", "after_first_page"] = "start",
    pdf_bytes: bytes | None = None,
) -> None:
    """Insert a TOC field pre-populated with entries, plus a PAGE footer.

    The field stays dirty so F9 still refreshes it in Word, but the entries between
    ``separate`` and ``end`` mean the reader sees a real table of contents on open
    instead of "right-click and update field".
    """
    seen: set[tuple[int, str]] = set()
    headings: list[tuple[int, str]] = []
    for paragraph in _iter_all_paragraphs(document):
        name = paragraph.style.name
        text = paragraph.text.strip()
        if name not in _HEADING_STYLES or not text:
            continue
        key = (int(name.split()[-1]), text)
        if key in seen:
            continue
        seen.add(key)
        headings.append(key)

    body = document._element.body
    toc_elements = []

    title = document.add_paragraph()
    title.style = document.styles["Title"]
    title.add_run("Mục lục")
    body.remove(title._p)
    toc_elements.append(title._p)

    opening = document.add_paragraph()
    _append_field_char(opening, "begin", dirty=True)
    _append_instr_text(opening, _TOC_INSTRUCTION)
    _append_field_char(opening, "separate")
    body.remove(opening._p)
    toc_elements.append(opening._p)

    page_numbers = _heading_page_numbers(pdf_bytes, headings)
    bookmark_id = _next_bookmark_id(document)
    for (level, text), page_number in zip(headings, page_numbers, strict=False):
        entry = document.add_paragraph()
        bookmark_id += 1
        bookmark_name = f"_Toc{bookmark_id:08d}"
        start_mark = OxmlElement("w:bookmarkStart")
        start_mark.set(qn("w:id"), str(bookmark_id))
        start_mark.set(qn("w:name"), bookmark_name)
        entry._p.append(start_mark)

        entry.add_run(text)
        entry.paragraph_format.tab_stops.add_tab_stop(
            Inches(6.5), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS
        )
        entry.add_run("	")
        _append_field_char(entry, "begin")
        _append_instr_text(entry, f" PAGEREF {bookmark_name} \\h ")
        _append_field_char(entry, "separate")
        entry.add_run(str(page_number))
        _append_field_char(entry, "end")

        end_mark = OxmlElement("w:bookmarkEnd")
        end_mark.set(qn("w:id"), str(bookmark_id))
        entry._p.append(end_mark)

        if level > 1:
            entry.paragraph_format.left_indent = Pt(18 * (level - 1))
        body.remove(entry._p)
        toc_elements.append(entry._p)

    closing = document.add_paragraph()
    _append_field_char(closing, "end")
    body.remove(closing._p)
    toc_elements.append(closing._p)

    page_break = OxmlElement("w:p")
    page_break.append(OxmlElement("w:pPr"))
    break_run = OxmlElement("w:r")
    break_element = OxmlElement("w:br")
    break_element.set(qn("w:type"), "page")
    break_run.append(break_element)
    page_break.append(break_run)
    toc_elements.append(page_break)

    anchor = _toc_anchor(body, toc_position)
    for offset, element in enumerate(toc_elements):
        body.insert(anchor + offset, element)

    _add_page_number_footer(document)

    settings = document.settings.element
    update_fields = settings.find(qn("w:updateFields"))
    if update_fields is None:
        update_fields = OxmlElement("w:updateFields")
        update_fields.set(qn("w:val"), "true")
        settings.insert(0, update_fields)


def _next_bookmark_id(document: Document) -> int:
    """One above the highest bookmark id already in the document."""
    ids = [
        int(mark.get(qn("w:id")))
        for mark in document.element.body.iter(qn("w:bookmarkStart"))
        if (mark.get(qn("w:id")) or "").lstrip("-").isdigit()
    ]
    return max(ids, default=0)


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
