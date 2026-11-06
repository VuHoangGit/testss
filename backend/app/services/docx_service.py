"""Sinh file Word (.docx) từ văn bản OCR mà **giữ cấu trúc** của tài liệu gốc.

Vì sao có module này: bản xuất Word trước đây chỉ đổ từng dòng thành paragraph
style "Normal", nên `##` do model OCR sinh ra và bảng Markdown hiện ra dưới
dạng ký tự thô; file .docx không có outline level nên mục lục (References →
Table of Contents) và Navigation Pane đều rỗng.

Ở đây văn bản được parse lại theo khối Markdown nhẹ rồi ghi bằng đúng style của
Word (mọi style dùng ở đây đều có sẵn trong template mặc định của python-docx):

- `#` … `######`        → Heading 1…6 (**có outline level** → TOC dựng được)
- bảng `| a | b |`      → table thật, style Table Grid, hàng đầu in đậm + lặp
                          lại khi bảng sang trang, tôn trọng `:---:` căn lề
- `- ` / `* ` / `+ `    → List Bullet (lồng nhau theo thụt đầu dòng)
- `1. ` / `1) `         → List Number (lồng nhau)
- `**đậm**`, `*nghiêng*`, `` `code` `` → run có định dạng tương ứng
- `> trích dẫn`         → style Quote
- `--- Trang N ---`     → ngắt trang (thay vì để mốc chữ thô trong bản Word)
- `[chữ ký tay]`, `[?]`, `[mất chữ]` → in nghiêng xám để dễ soi lại bản gốc
- `Hình 1.` / `Bảng 2:` → style Caption (Word dựng được Table of Figures)

Tài liệu không có `#` nào (PDF lớp text trích bằng pypdf mất hết cỡ chữ) thì
đoán tiêu đề theo mẫu văn bản hành chính VN: "CHƯƠNG/PHẦN …" → Heading 1,
"Điều N …" → Heading 2. Chỉ đoán khi không có marker sẵn, để không đè lên kết
quả phân tích của model OCR.
"""

import io
import re

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docx.text.paragraph import Paragraph

# Màu cho chỗ model đánh dấu không đọc được — nhìn là thấy ngay khi soát bản gốc.
_MARKER_COLOR = RGBColor(0x80, 0x80, 0x80)
_CODE_FONT = "Consolas"
_CODE_SIZE = Pt(10)
# Tiêu đề dài quá mức này thì nhiều khả năng là đoạn văn bị xuống dòng, không
# phải tiêu đề → không nâng thành heading.
_MAX_HEADING_CHARS = 120

# Mỗi cấp mục lục thụt vào bấy nhiêu cm (template mặc định không có style
# "TOC 1…9" nên thụt lề bằng định dạng trực tiếp).
_TOC_INDENT_CM = 0.6

_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<text>.*\S)\s*$")
_PAGE_MARKER_RE = re.compile(r"^-{3,}\s*(?:Trang|Page)\s+(?P<page>\d+)\s*-{3,}$", re.IGNORECASE)
_BULLET_RE = re.compile(r"^(?P<indent>[ \t]*)[-*+•–—]\s+(?P<text>.*\S)$")
_ORDERED_RE = re.compile(r"^(?P<indent>[ \t]*)\d{1,3}[.)]\s+(?P<text>.*\S)$")
_QUOTE_RE = re.compile(r"^[ \t]*>[ \t]?(?P<text>.*\S)?\s*$")
_FENCE_RE = re.compile(r"^[ \t]*```.*$")
# Dòng kẻ ngang (`---`, `***`) — dấu phân cách, không phải nội dung. Không tính
# `___` vì trong biểu mẫu đó thường là chỗ trống để điền tay, phải giữ lại.
_RULE_RE = re.compile(r"^(?:[-*][ \t]*){3,}$")
_DIVIDER_CELL_RE = re.compile(r"^:?-{2,}:?$")
_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")
_CAPTION_RE = re.compile(
    r"^(?:Hình|Hình\s+ảnh|Bảng|Biểu\s+đồ|Sơ\s+đồ|Figure|Table|Chart)\s*\d+",
    re.IGNORECASE,
)
# Chỗ model ghi chú thay vì chép chữ: [?], [mất chữ], [chữ ký tay], [dấu đỏ tròn]…
_OCR_MARKER_RE = re.compile(r"\[[^\]\d][^\]]{0,79}\]")
# Định dạng nội tuyến trong một dòng. Dấu `*`/`_` chỉ tính là đánh dấu khi nằm ở
# ranh giới từ — nếu không, "5*3 và 4*2" hay "snake_case" sẽ bị hiểu sai.
_INLINE_RE = re.compile(
    r"(\*\*(?=\S)[^*\n]+?(?<=\S)\*\*"
    r"|__(?=\S)[^_\n]+?(?<=\S)__"
    r"|`[^`\n]+`"
    r"|(?<![\w*])\*(?=\S)[^*\n]+?(?<=\S)\*(?![\w*])"
    r"|(?<![\w_])_(?=\S)[^_\n]+?(?<=\S)_(?![\w_]))"
)
# Đoán tiêu đề cho văn bản không có marker Markdown (PDF lớp text).
_CHAPTER_RE = re.compile(r"^(?:PHẦN|CHƯƠNG|Phần|Chương)\s+[IVXLC\d]+", re.IGNORECASE)
_ARTICLE_RE = re.compile(r"^(?:ĐIỀU|Điều)\s+\d+", re.IGNORECASE)
# Dấu kết câu — dòng tiêu đề thường không có, dòng văn xuôi thì có.
_SENTENCE_END = (".", ",", ";", ":")
# Dấu kết thúc **đoạn văn** (khác _SENTENCE_END: dấu phẩy không kết thúc đoạn).
_PARAGRAPH_END = (".", "!", "?", ":", ";", "…", "”", '"', ")", "]")
# Ký tự điều khiển — XML 1.0 không cho phép (tab/xuống dòng đã xử lý riêng).
_XML_ILLEGAL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def to_docx_bytes(text: str, *, title: str | None = None, include_toc: bool = True) -> bytes:
    """Văn bản OCR (Markdown nhẹ) → nội dung file .docx.

    `title` ghi vào thuộc tính file (Word hiện ở title bar / metadata);
    `include_toc` chèn mục lục tự động khi tài liệu có từ 2 tiêu đề trở lên.
    """
    buffer = io.BytesIO()
    build_document(text, title=title, include_toc=include_toc).save(buffer)
    return buffer.getvalue()


def build_document(text: str, *, title: str | None = None, include_toc: bool = True) -> Document:
    """Dựng đối tượng Document (chưa ghi ra bytes) — dùng cho test và xuất file."""
    lines = _prepare_lines(text)
    if not any(_HEADING_RE.match(line) for line in lines):
        lines = _infer_headings(lines)
    lines = _promote_heading_levels(lines)

    document = Document()
    _setup_page(document)
    if title:
        document.core_properties.title = title

    headings = _collect_headings(lines)
    if include_toc and len(headings) >= 2:
        _add_table_of_contents(document, headings)

    _render_lines(document, lines)
    _add_page_numbers(document)
    return document


# ---------------------------------------------------------------------------
# Chuẩn hoá đầu vào


def _prepare_lines(text: str) -> list[str]:
    """Tách dòng, bỏ hàng rào ``` và ký tự rác; giữ nguyên thụt đầu dòng."""
    lines: list[str] = []
    for raw in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if _FENCE_RE.match(raw):
            continue
        line = raw.rstrip().replace("\t", "  ")
        line = _clean_glyphs(line)
        if line.strip():
            # "##Tiêu đề" (model quên dấu cách) vẫn là heading; giữ nguyên thụt
            # đầu dòng vì nó là mức lồng của danh sách.
            line = re.sub(r"^(\s*#{1,6})(?=[^#\s])", r"\1 ", line)
        lines.append(line)
    return lines


def _clean_glyphs(line: str) -> str:
    """Đổi/bỏ ký tự mà XML không nhận — gặp là python-docx ném ValueError (HTTP 500).

    U+FFFE là "non-character" nhưng nhiều PDF dùng nó cho glyph dấu gạch nối khi
    ngắt dòng ("Non￾Linear"); đường trích bằng pdfium đã đổi sẵn, còn đường dự
    phòng pypdf thì để nguyên nên phải chặn ở đây.
    """
    return _XML_ILLEGAL_RE.sub("", line.replace("￾", "-").replace("￿", ""))


def _promote_heading_levels(lines: list[str]) -> list[str]:
    """Dịch cấp heading để cấp nông nhất trở thành `#` (Heading 1).

    Model OCR thường chỉ ghi `##`/`###` (không có `#`), còn tài liệu cùng một
    cỡ tiêu đề thì suy ra toàn cấp 2. Giữ nguyên sẽ làm cả cây outline lùi một
    cấp: mục lục vẫn dựng được nhưng sai thứ bậc so với bản gốc. Dịch lên cho
    tiêu đề ngoài cùng thành Heading 1, tương quan giữa các cấp không đổi.
    """
    levels = [
        len(match.group("hashes"))
        for line in lines
        if (match := _HEADING_RE.match(line.strip()))
    ]
    shift = min(levels, default=1) - 1
    if shift <= 0:
        return lines

    result: list[str] = []
    for line in lines:
        match = _HEADING_RE.match(line.strip())
        if match is None:
            result.append(line)
            continue
        indent = line[: len(line) - len(line.lstrip())]
        level = len(match.group("hashes")) - shift
        result.append(f"{indent}{'#' * level} {match.group('text')}")
    return result


def _collect_headings(lines: list[str]) -> list[tuple[int, str]]:
    """`(cấp, chữ tiêu đề)` của mọi dòng heading — nguồn dựng mục lục."""
    result: list[tuple[int, str]] = []
    for line in lines:
        match = _HEADING_RE.match(line.strip())
        if match:
            result.append((len(match.group("hashes")), match.group("text")))
    return result


def _infer_headings(lines: list[str]) -> list[str]:
    """Đoán tiêu đề theo mẫu văn bản hành chính cho tài liệu không có `#`."""
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        level = 0
        if (
            stripped
            and len(stripped) <= _MAX_HEADING_CHARS
            and not stripped.endswith(_SENTENCE_END)
        ):
            if _CHAPTER_RE.match(stripped):
                level = 1
            elif _ARTICLE_RE.match(stripped):
                level = 2
        result.append(f"{'#' * level} {stripped}" if level else line)
    return result


# ---------------------------------------------------------------------------
# Trang, mục lục, số trang


def _setup_page(document: Document) -> None:
    """Khổ A4 (chuẩn văn bản VN) thay cho Letter mặc định của python-docx."""
    section = document.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.0)


def _add_table_of_contents(document: Document, headings: list[tuple[int, str]]) -> None:
    """Chèn mục lục: field TOC **kèm kết quả có sẵn** là danh sách tiêu đề.

    Trước đây phần kết quả của field chỉ là một câu placeholder, nên trình đọc
    không tự tính lại field (WPS, Google Docs, viewer điện thoại) hiện đúng câu
    đó và người dùng thấy như file lỗi. Nay kết quả là chính các tiêu đề (thụt
    theo cấp) — luôn đọc được; Word/Office cập nhật field sẽ thay bằng mục lục
    đầy đủ kèm số trang và liên kết (cờ `updateFields` bật sẵn).
    """
    _paragraph_with_text(document, "Mục lục", style="Title")
    entries: list[Paragraph] = []
    for level, text in headings:
        entry = document.add_paragraph()
        entry.paragraph_format.left_indent = Cm(_TOC_INDENT_CM * (level - 1))
        if not entries:
            # begin/separate nằm ngay trong dòng mục lục đầu tiên (như Word
            # ghi) để không sinh thêm dòng trống trên đầu mục lục.
            _append_field_begin(entry, ' TOC \\o "1-3" \\h \\z \\u ')
        _add_inline(entry, text)
        entries.append(entry)
    if entries:  # đầu vào đã đảm bảo ≥ 2 tiêu đề, đây chỉ là chốt an toàn
        _append_field_end(entries[-1])
    document.add_page_break()
    _enable_field_update(document)


# Theo ECMA-376, `w:updateFields` phải đứng trước các phần tử này trong
# settings.xml; chèn sai thứ tự là Word báo file hỏng.
_SETTINGS_AFTER_UPDATE_FIELDS = (
    "w:hdrShapeDefaults",
    "w:footnotePr",
    "w:endnotePr",
    "w:compat",
    "w:docVars",
    "w:rsids",
    "w:mathPr",
    "w:themeFontLang",
    "w:clrSchemeMapping",
    "w:shapeDefaults",
    "w:decimalSymbol",
    "w:listSeparator",
)


def _enable_field_update(document: Document) -> None:
    """Bật cờ updateFields để Word tính lại mục lục ngay khi mở file."""
    settings = document.settings.element
    if settings.find(qn("w:updateFields")) is not None:
        return
    update = OxmlElement("w:updateFields")
    update.set(qn("w:val"), "true")
    for tag in _SETTINGS_AFTER_UPDATE_FIELDS:
        anchor = settings.find(qn(tag))
        if anchor is not None:
            anchor.addprevious(update)
            return
    settings.append(update)


def _add_page_numbers(document: Document) -> None:
    """Chân trang: số trang (field PAGE) — bản Word nhiều trang vẫn đọc được."""
    for section in document.sections:
        paragraph = section.footer.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _append_field(paragraph, " PAGE ", "1")


def _append_field(paragraph: Paragraph, instruction: str, placeholder: str) -> None:
    """Ghi một field Word một dòng (PAGE…) với kết quả có sẵn là `placeholder`."""
    _append_field_begin(paragraph, instruction)
    paragraph.add_run(placeholder)
    _append_field_end(paragraph)


def _append_field_begin(paragraph: Paragraph, instruction: str) -> None:
    """Mở field: `begin` (dirty) → `instrText` → `separate`.

    Kết quả của field là các run ghi sau lời gọi này (với TOC: nhiều dòng tiêu
    đề, có thể trải nhiều paragraph) cho tới [_append_field_end].
    """
    _field_mark(paragraph, "begin")
    run = paragraph.add_run()
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    run._r.append(instr)  # noqa: SLF001 — python-docx không có API cho field
    _field_mark(paragraph, "separate")


def _append_field_end(paragraph: Paragraph) -> None:
    """Đóng field ở paragraph cuối cùng của phần kết quả."""
    _field_mark(paragraph, "end")


def _field_mark(paragraph: Paragraph, kind: str) -> None:
    """Ranh giới field (begin/separate/end) theo đúng cú pháp OOXML."""
    run = paragraph.add_run()
    mark = OxmlElement("w:fldChar")
    mark.set(qn("w:fldCharType"), kind)
    if kind == "begin":
        mark.set(qn("w:dirty"), "true")
    run._r.append(mark)  # noqa: SLF001


# ---------------------------------------------------------------------------
# Render


def _render_lines(document: Document, lines: list[str]) -> None:
    """Duyệt từng dòng và ghi khối tương ứng (bảng chiếm nhiều dòng liền nhau).

    Các dòng văn xuôi liền nhau được gộp thành **một** paragraph: bản PDF cắt
    mỗi dòng hình ảnh thành một dòng văn bản, ghi nguyên xi thì đoạn văn vụn
    đúng bằng số dòng bản gốc (tài liệu 10 trang ra 19 trang Word, câu bị ngắt
    giữa dòng). Ngắt đoạn khi dòng trước đã hết câu, gặp dòng trống, hoặc gặp
    khối khác (heading, bảng, danh sách, trích dẫn, ngắt trang).
    """
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            _add_paragraph(document, _join_paragraph_lines(buffer))
            buffer.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            flush()
            index += 1
            continue

        if _PAGE_MARKER_RE.match(stripped):
            flush()
            document.add_page_break()
            index += 1
            continue

        if _RULE_RE.match(stripped):  # dòng kẻ phân cách: bỏ, không thành chữ
            index += 1
            continue

        if _is_table_start(lines, index):
            flush()
            index = _add_table(document, lines, index)
            continue

        heading = _HEADING_RE.match(stripped)
        if heading:
            flush()
            _add_heading(document, heading.group("text"), len(heading.group("hashes")))
            index += 1
            continue

        bullet = _BULLET_RE.match(line)
        if bullet:
            flush()
            _add_list_item(
                document, bullet.group("text"), ordered=False, indent=bullet.group("indent")
            )
            index += 1
            continue

        ordered = _ORDERED_RE.match(line)
        if ordered:
            flush()
            _add_list_item(
                document, ordered.group("text"), ordered=True, indent=ordered.group("indent")
            )
            index += 1
            continue

        quote = _QUOTE_RE.match(line)
        if quote:
            flush()
            _add_paragraph(document, quote.group("text") or "", style="Quote")
            index += 1
            continue

        if _CAPTION_RE.match(stripped):
            flush()
            paragraph = _add_paragraph(document, stripped, style="Caption")
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            index += 1
            continue

        # Dòng văn xuôi: dòng trước đã hết câu thì đây là đoạn mới.
        stray_pipe = _is_stray_pipe_line(stripped)
        if buffer and (_ends_argument(buffer[-1]) or stray_pipe):
            flush()
        buffer.append(stripped)
        if stray_pipe:  # dòng kẻ/bảng hỏng: đứng riêng, không dính với văn xuôi
            flush()
        index += 1

    flush()


def _ends_argument(line: str) -> bool:
    """Dòng đã kết thúc một đoạn văn (dấu kết câu) → dòng sau là đoạn mới."""
    return line.rstrip().endswith(_PARAGRAPH_END)


def _is_stray_pipe_line(line: str) -> bool:
    """Dòng bắt đầu bằng `|` nhưng không đủ thành bảng (model OCR hay trả về).

    Giữ nguyên dòng đó thành một paragraph riêng: nối nó vào câu văn bên cạnh
    sẽ thành "| chỉ một dòng | Đoạn sau." — sai cả nội dung lẫn hình thức.
    """
    return line.startswith("|")


def _join_paragraph_lines(parts: list[str]) -> str:
    """Ghép các dòng của cùng một đoạn; gạch nối cuối dòng thì nối liền chữ."""
    text = parts[0]
    for part in parts[1:]:
        text = text + part if text.endswith("-") else f"{text} {part}"
    return text


def _add_heading(document: Document, text: str, level: int) -> None:
    """Heading 1…6 — style chuẩn của Word nên có outline level cho mục lục."""
    paragraph = document.add_heading("", level=min(max(level, 1), 6))
    _add_inline(paragraph, text)
    paragraph.paragraph_format.keep_with_next = True


def _add_paragraph(document: Document, text: str, *, style: str | None = None) -> Paragraph:
    """Paragraph thường (hoặc style chỉ định) với định dạng nội tuyến đầy đủ."""
    paragraph = document.add_paragraph(style=style) if style else document.add_paragraph()
    _add_inline(paragraph, text)
    return paragraph


def _paragraph_with_text(document: Document, text: str, *, style: str) -> Paragraph:
    """Paragraph có style cho trước, chữ thuần (không parse Markdown)."""
    paragraph = document.add_paragraph(style=style)
    paragraph.add_run(text)
    return paragraph


def _list_level(indent: str) -> int:
    """Mức lồng của mục danh sách: 2 space = 1 cấp (giới hạn 3 style có sẵn)."""
    return min(len(indent) // 2, 2)


def _add_list_item(document: Document, text: str, *, ordered: bool, indent: str) -> None:
    """Mục danh sách dùng style List Bullet/List Number (có sẵn numbering)."""
    base = "List Number" if ordered else "List Bullet"
    level = _list_level(indent)
    style = base if level == 0 else f"{base} {level + 1}"
    paragraph = document.add_paragraph(style=style)
    _add_inline(paragraph, text)


# ---------------------------------------------------------------------------
# Bảng


def _is_table_start(lines: list[str], index: int) -> bool:
    """Bảng = dòng `| … |` có dòng `| … |` hoặc `|---|---|` ngay sau.

    Model OCR thường bỏ dòng phân cách, nên chỉ cần 2 dòng liền nhau bắt đầu
    bằng `|` là coi là bảng; có dòng phân cách thì mới in đậm hàng đầu.
    """
    if not lines[index].strip().startswith("|"):
        return False
    if index + 1 >= len(lines):
        return False
    following = lines[index + 1].strip()
    return following.startswith("|") or _is_divider_row(following)


def _is_divider_row(line: str) -> bool:
    cells = _split_row(line)
    return bool(cells) and all(_DIVIDER_CELL_RE.match(cell) for cell in cells)


def _split_row(line: str) -> list[str]:
    """Tách ô của một dòng bảng; `\\|` là ký tự | trong nội dung, không phải ô."""
    row = line.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    return [cell.strip().replace("\\|", "|") for cell in _CELL_SPLIT_RE.split(row)]


def _cell_alignment(cell: str) -> WD_ALIGN_PARAGRAPH | None:
    """Căn lề cột theo `:---`, `:---:`, `---:` trong dòng phân cách."""
    left, right = cell.startswith(":"), cell.endswith(":")
    if left and right:
        return WD_ALIGN_PARAGRAPH.CENTER
    if right:
        return WD_ALIGN_PARAGRAPH.RIGHT
    if left:
        return WD_ALIGN_PARAGRAPH.LEFT
    return None


def _add_table(document: Document, lines: list[str], index: int) -> int:
    """Ghi bảng Markdown thành table thật; trả index của dòng đầu tiên sau bảng."""
    header = _split_row(lines[index])
    has_divider = _is_divider_row(lines[index + 1])
    alignments = (
        [_cell_alignment(cell) for cell in _split_row(lines[index + 1])] if has_divider else []
    )
    body: list[list[str]] = []
    cursor = index + 2 if has_divider else index + 1
    while cursor < len(lines) and lines[cursor].strip().startswith("|"):
        body.append(_split_row(lines[cursor]))
        cursor += 1

    columns = max([len(header), *(len(row) for row in body)] or [len(header)])
    rows = [header, *body]
    table = document.add_table(rows=len(rows), cols=max(columns, 1))
    table.style = "Table Grid"

    for row_index, row in enumerate(rows):
        for column in range(columns):
            cell = table.cell(row_index, column)
            text = row[column] if column < len(row) else ""
            paragraph = cell.paragraphs[0]
            _add_inline(paragraph, text, bold=row_index == 0)
            alignment = alignments[column] if column < len(alignments) else None
            if alignment is not None:
                paragraph.alignment = alignment

    # Hàng đầu lặp lại ở mỗi trang — bảng dài vẫn đọc được.
    header_properties = table.rows[0]._tr.get_or_add_trPr()  # noqa: SLF001
    repeat = OxmlElement("w:tblHeader")
    repeat.set(qn("w:val"), "true")
    header_properties.append(repeat)

    # Cách bảng một dòng trống cho khỏi dính vào đoạn văn kế tiếp.
    document.add_paragraph()
    return cursor


# ---------------------------------------------------------------------------
# Định dạng nội tuyến


def _add_inline(paragraph: Paragraph, text: str, *, bold: bool = False) -> None:
    """Ghi một dòng có `**đậm**`, `*nghiêng*`, `` `code` `` thành các run."""
    position = 0
    for match in _INLINE_RE.finditer(text):
        if match.start() > position:
            _add_text_run(paragraph, text[position : match.start()], bold=bold)
        token = match.group(0)
        if token.startswith(("**", "__")):
            _add_text_run(paragraph, token[2:-2], bold=True)
        elif token.startswith("`"):
            _add_code_run(paragraph, token[1:-1])
        else:
            _add_text_run(paragraph, token[1:-1], italic=True, bold=bold)
        position = match.end()
    if position < len(text):
        _add_text_run(paragraph, text[position:], bold=bold)


def _add_text_run(
    paragraph: Paragraph, text: str, *, bold: bool = False, italic: bool = False
) -> None:
    """Ghi chữ thuần; chỗ model đánh dấu không đọc được thì in nghiêng xám."""
    position = 0
    for match in _OCR_MARKER_RE.finditer(text):
        if match.start() > position:
            _write_run(paragraph, text[position : match.start()], bold=bold, italic=italic)
        marker = _write_run(paragraph, match.group(0), italic=True)
        marker.font.color.rgb = _MARKER_COLOR
        position = match.end()
    if position < len(text):
        _write_run(paragraph, text[position:], bold=bold, italic=italic)


def _write_run(paragraph: Paragraph, text: str, *, bold: bool = False, italic: bool = False):
    """Tạo run với đúng thuộc tính cần bật (không set False cho khỏi nặng XML)."""
    run = paragraph.add_run(text)
    if bold:
        run.bold = True
    if italic:
        run.italic = True
    return run


def _add_code_run(paragraph: Paragraph, text: str) -> None:
    """Mã inline: font đẳng khoảng để không bị lẫn với văn xuôi."""
    run = paragraph.add_run(text)
    run.font.name = _CODE_FONT
    run.font.size = _CODE_SIZE
    # font.name chỉ đặt w:ascii; tiếng Việt dùng w:hAnsi (và w:cs cho ký tự CJK)
    fonts = run._r.get_or_add_rPr().get_or_add_rFonts()  # noqa: SLF001
    fonts.set(qn("w:hAnsi"), _CODE_FONT)
    fonts.set(qn("w:cs"), _CODE_FONT)
