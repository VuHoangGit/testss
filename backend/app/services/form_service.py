"""Sinh biểu mẫu có logo cho PDF, DOCX và DOC."""

from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Iterable
from pathlib import Path

import pymupdf
from docx import Document
from docx.shared import Mm
from PIL import Image

SUPPORTED_TEMPLATE_TYPES = {".pdf", ".docx", ".doc"}

# Placement 3 phần tử (bytes, x, y) — cũ; 5 phần tử (bytes, x, y, w, h) — WYSIWYG.
LogoPlacement = tuple[bytes, float, float] | tuple[bytes, float, float, float, float]

# Chữ ký đầu tệp — dùng để chặn tệp đính kèm đổi đuôi (vd. .txt → .pdf).
_PDF_MAGIC = b"%PDF"
_ZIP_MAGIC = b"PK\x03\x04"  # DOCX là file ZIP (OOXML)
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # .doc nhị phân cũ
_RTF_MAGIC = b"{\\rtf"  # .doc lưu dạng RTF

# Ký tự không hợp lệ trong tên tệp trên Windows và ký tự điều khiển.
_INVALID_NAME_CHARS = frozenset('<>:"/\\|?*')

# Định dạng đầu ra người dùng chọn. None = giữ nguyên định dạng tệp gốc.
OUTPUT_MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def templates_dir(configured_dir: str) -> Path:
    directory = Path(configured_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def list_templates(configured_dir: str) -> list[dict[str, object]]:
    directory = templates_dir(configured_dir)
    templates: list[dict[str, object]] = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_TEMPLATE_TYPES:
            continue
        templates.append(
            {
                "name": path.name,
                "size_bytes": path.stat().st_size,
                "type": path.suffix.lower().lstrip("."),
            }
        )
    return templates


def normalize_output_format(value: str | None) -> str | None:
    """Chuẩn hoá lựa chọn định dạng xuất. None = giữ nguyên định dạng gốc."""
    if value is None or not value.strip():
        return None
    fmt = value.strip().lower()
    if fmt == "word":
        fmt = "docx"
    if fmt not in OUTPUT_MIME:
        raise ValueError("Định dạng xuất chỉ hỗ trợ PDF hoặc DOCX")
    return fmt


def resolve_template(configured_dir: str, template_name: str) -> Path:
    directory = templates_dir(configured_dir).resolve()
    candidate = (directory / template_name).resolve()
    if candidate.parent != directory:
        raise ValueError("Tên biểu mẫu không hợp lệ")
    if candidate.suffix.lower() not in SUPPORTED_TEMPLATE_TYPES:
        raise ValueError("Định dạng biểu mẫu không được hỗ trợ")
    if not candidate.is_file():
        raise FileNotFoundError("Không tìm thấy biểu mẫu")
    return candidate


def sanitize_upload_name(raw_name: str | None) -> str:
    """Chuẩn hoá tên tệp người dùng đính kèm.

    Bỏ mọi thành phần đường dẫn (chặn ``../../etc/passwd``), thay ký tự không
    hợp lệ trong tên tệp, và chỉ cho 3 đuôi hỗ trợ.
    """
    name = (raw_name or "").replace("\\", "/").split("/")[-1].strip()
    if not name or name in {".", ".."}:
        raise ValueError("Thiếu tên tệp đính kèm")
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED_TEMPLATE_TYPES:
        raise ValueError("Chỉ hỗ trợ tệp PDF, DOCX hoặc DOC")
    stem = name[: len(name) - len(suffix)]
    cleaned = "".join(
        "_" if char in _INVALID_NAME_CHARS or ord(char) < 32 else char for char in stem
    ).strip(" .")
    return f"{cleaned or 'bieu-mau'}{suffix}"


def validate_upload(file_name: str | None, file_bytes: bytes) -> tuple[str, bytes]:
    """Trả (tên an toàn, nội dung) sau khi kiểm tra đuôi và chữ ký đầu tệp."""
    name = sanitize_upload_name(file_name)
    if not file_bytes:
        raise ValueError("Tệp đính kèm rỗng")
    head = file_bytes[:8]
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf" and file_bytes.lstrip()[:4] != _PDF_MAGIC:
        raise ValueError("Tệp đính kèm không phải PDF hợp lệ")
    if suffix == ".docx" and not head.startswith(_ZIP_MAGIC):
        raise ValueError("Tệp đính kèm không phải DOCX hợp lệ")
    if suffix == ".doc" and not (head == _OLE_MAGIC or head.startswith(_RTF_MAGIC)):
        raise ValueError("Tệp đính kèm không phải DOC hợp lệ")
    return name, file_bytes


def validate_logo(logo_bytes: bytes) -> tuple[bytes, str]:
    if not logo_bytes:
        raise ValueError("Logo không được để trống")
    try:
        image = Image.open(io.BytesIO(logo_bytes))
        image.verify()
    except Exception as exc:
        raise ValueError("Logo không phải PNG/JPEG hợp lệ") from exc
    if image.format not in {"PNG", "JPEG"}:
        raise ValueError("Logo chỉ hỗ trợ PNG hoặc JPEG")
    return logo_bytes, "png" if image.format == "PNG" else "jpg"


def _add_logo_to_docx(
    source: Path,
    logo: bytes,
    output: Path,
    x: float = 0.82,
    y: float = 0.04,
    is_watermark: bool = False,
    logo_placements: Iterable[LogoPlacement] | None = None,
) -> None:
    document = Document(str(source))
    for section in document.sections:
        section.header.is_linked_to_previous = False
        header = section.header
        table = header.add_table(rows=1, cols=2, width=section.page_width)
        table.columns[0].width = section.page_width - Mm(42)
        table.columns[1].width = Mm(42)
        table.autofit = False
        left = table.rows[0].cells[0]
        left.width = section.page_width - Mm(42)
        right = table.rows[0].cells[1]
        right.width = Mm(42)
        right.vertical_alignment = 1
        paragraph = right.paragraphs[0]
        paragraph.alignment = 2
        placements = logo_placements or ((logo, x, y),)
        for entry in placements:
            placed_logo = entry[0]
            run = paragraph.add_run()
            run.add_picture(
                io.BytesIO(placed_logo),
                width=Mm(38),
                height=Mm(16),
            )

        # Translate normalized coordinates to usable-page dimensions.
        usable_width = section.page_width - section.left_margin - section.right_margin
        usable_height = section.page_height - section.top_margin - section.bottom_margin
        usable_height_mm = usable_height / 36000
        section.header_distance = Mm(max(0.0, y * usable_height_mm))
        left_width = int(usable_width * max(0.0, min(1.0, x)))
        table.columns[0].width = left_width
        table.columns[1].width = usable_width - left_width

        if is_watermark:
            for existing in header.paragraphs:
                existing.paragraph_format.line_spacing = 1.0
    document.save(str(output))


def _convert_doc_to_docx(source: Path, work_dir: Path) -> Path:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError("Thiết bị chưa cài LibreOffice. Cần soffice để chuyển DOC sang DOCX.")
    work_dir.mkdir(parents=True, exist_ok=True)
    profile = work_dir / "lo-profile"
    profile.mkdir(exist_ok=True)
    command = [
        soffice,
        f"-env:UserInstallation=file:///{profile.as_posix()}",
        "--headless",
        "--convert-to",
        "docx",
        "--outdir",
        str(work_dir),
        str(source),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("LibreOffice chuyển DOC quá thời gian") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(detail or "LibreOffice không chuyển được DOC")

    converted = work_dir / f"{source.stem}.docx"
    if not converted.is_file():
        raise RuntimeError("LibreOffice không tạo được file DOCX")
    return converted


def _transparent_tiled_logo(logo: bytes, page_width: float, page_height: float) -> bytes:
    image = Image.open(io.BytesIO(logo)).convert("RGBA")
    max_width = max(80, int(page_width * 0.24))
    ratio = max_width / image.width
    tile_width = max_width
    tile_height = max(40, int(image.height * ratio))
    tile = image.resize((tile_width, tile_height), Image.Resampling.LANCZOS)
    alpha = tile.getchannel("A").point(lambda value: int(value * 0.12))
    tile.putalpha(alpha)

    canvas = Image.new("RGBA", (int(page_width), int(page_height)), (0, 0, 0, 0))
    step_x = tile_width + 120
    step_y = tile_height + 100
    for top in range(80, int(page_height), step_y):
        for left in range(20, int(page_width), step_x):
            canvas.alpha_composite(tile, (left, top))
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()


def _add_logo_to_pdf(
    source: Path,
    logo: bytes,
    output: Path,
    x: float = 0.82,
    y: float = 0.04,
    is_watermark: bool = False,
    password: str | None = None,
    logo_placements: Iterable[LogoPlacement] | None = None,
) -> None:
    with pymupdf.open(str(source)) as document:
        if document.is_encrypted:
            raise ValueError("PDF mẫu đang được bảo vệ bằng mật khẩu")
        if document.page_count == 0:
            raise ValueError("PDF mẫu không có trang")

        for page in document:
            rect = page.rect
            if is_watermark:
                for watermark_logo, *_ in logo_placements or ((logo, x, y),):
                    page.insert_image(
                        rect,
                        stream=_transparent_tiled_logo(
                            watermark_logo,
                            rect.width,
                            rect.height,
                        ),
                        overlay=True,
                        keep_proportion=True,
                    )
            else:
                placements = logo_placements or ((logo, x, y),)
                for entry in placements:
                    placed_logo = entry[0]
                    placed_x = float(entry[1])
                    placed_y = float(entry[2])
                    placed_w = float(entry[3]) if len(entry) > 3 and entry[3] else None
                    placed_h = float(entry[4]) if len(entry) > 4 and entry[4] else None
                    image = Image.open(io.BytesIO(placed_logo))
                    image.verify()
                    image = Image.open(io.BytesIO(placed_logo))
                    width_px, height_px = image.size
                    if placed_w and placed_h:
                        # WYSIWYG: đúng kích thước hộp đã kéo thả trên preview.
                        box_width = min(placed_w * rect.width, rect.width)
                        box_height = min(placed_h * rect.height, rect.height)
                        # BoxFit.contain như frontend: giữ tỉ lệ ảnh, căn giữa trong hộp.
                        scale = min(box_width / width_px, box_height / height_px)
                        disp_width = width_px * scale
                        disp_height = height_px * scale
                        dx = (box_width - disp_width) / 2
                        dy = (box_height - disp_height) / 2
                    else:
                        max_width = rect.width * 0.18
                        max_height = rect.height * 0.08
                        scale = min(max_width / width_px, max_height / height_px)
                        box_width = max(32.0, width_px * scale)
                        box_height = max(18.0, height_px * scale)
                        dx = dy = 0.0
                        disp_width = box_width
                        disp_height = box_height
                    left = min(
                        rect.width - box_width,
                        max(0.0, placed_x * rect.width),
                    )
                    top = min(
                        rect.height - box_height,
                        max(0.0, placed_y * rect.height),
                    )
                    logo_rect = pymupdf.Rect(
                        left + dx,
                        top + dy,
                        left + dx + disp_width,
                        top + dy + disp_height,
                    )
                    page.insert_image(
                        logo_rect,
                        stream=placed_logo,
                        overlay=True,
                        keep_proportion=False,
                    )
        save_options: dict[str, object] = {"garbage": 4, "deflate": True}
        if password:
            save_options.update(
                {
                    "encryption": pymupdf.PDF_ENCRYPT_AES_256,
                    "owner_pw": "admin",
                    "user_pw": password,
                }
            )
        document.save(str(output), **save_options)


def _process_source(
    *,
    source: Path,
    logo_bytes: bytes,
    x: float = 0.82,
    y: float = 0.04,
    is_watermark: bool = False,
    password: str | None = None,
    logo_placements: Iterable[LogoPlacement] | None = None,
    output_format: str | None = None,
) -> tuple[bytes, str, str]:
    """Đóng logo lên một tệp nguồn bất kỳ (đã nằm trên đĩa).

    Dùng chung cho biểu mẫu có sẵn trong thư mục cấu hình và tệp người dùng
    đính kèm — hai đường vào, một đường xử lý.

    ``output_format``: ``None`` giữ nguyên định dạng gốc, hoặc ``"pdf"`` /
    ``"docx"`` để chuyển đổi. Đổi định dạng luôn đi qua bước trung gian chất
    lượng cao nhất: DOCX→PDF in bằng LibreOffice rồi đóng logo bằng PyMuPDF
    (giữ đúng khung kéo thả); PDF→DOCX dựng lại bằng service PDF→Word của dự án.
    """
    logo_bytes, _ = validate_logo(logo_bytes)
    target = normalize_output_format(output_format)
    suffix = source.suffix.lower()
    want = target or ("pdf" if suffix == ".pdf" else "docx")

    if target == "docx" and password:
        raise ValueError("Mật khẩu bảo vệ chỉ áp dụng cho PDF — hãy chọn định dạng xuất PDF")

    with tempfile.TemporaryDirectory(prefix="docuvault-logo-") as temp:
        work_dir = Path(temp)

        if want == "pdf":
            # soffice tự nhận .doc lẫn .docx → 1 lần gọi thay vì 2.
            pdf_source = source if suffix == ".pdf" else _convert_to_pdf(source, work_dir / "pdf")
            output = work_dir / f"{source.stem}-logo.pdf"
            _add_logo_to_pdf(
                pdf_source,
                logo_bytes,
                output,
                x=x,
                y=y,
                is_watermark=is_watermark,
                password=password,
                logo_placements=logo_placements,
            )
            return output.read_bytes(), output.name, OUTPUT_MIME["pdf"]

        if suffix == ".pdf":
            docx_source = _convert_pdf_to_docx(source, work_dir / "convert")
        elif suffix == ".doc":
            docx_source = _convert_doc_to_docx(source, work_dir / "convert")
        else:
            docx_source = source
        output = work_dir / f"{source.stem}-logo.docx"
        _add_logo_to_docx(
            docx_source,
            logo_bytes,
            output,
            x=x,
            y=y,
            is_watermark=is_watermark,
            logo_placements=logo_placements,
        )
        return output.read_bytes(), output.name, OUTPUT_MIME["docx"]


def process_template(
    *,
    configured_dir: str,
    template_name: str,
    logo_bytes: bytes,
    x: float = 0.82,
    y: float = 0.04,
    is_watermark: bool = False,
    password: str | None = None,
    logo_placements: Iterable[LogoPlacement] | None = None,
    output_format: str | None = None,
) -> tuple[bytes, str, str]:
    """Biểu mẫu có sẵn trong thư mục cấu hình. Trả (bytes, tên file, MIME)."""
    source = resolve_template(configured_dir, template_name)
    return _process_source(
        source=source,
        logo_bytes=logo_bytes,
        x=x,
        y=y,
        is_watermark=is_watermark,
        password=password,
        logo_placements=logo_placements,
        output_format=output_format,
    )


def process_uploaded_template(
    *,
    file_name: str | None,
    file_bytes: bytes,
    logo_bytes: bytes,
    x: float = 0.82,
    y: float = 0.04,
    is_watermark: bool = False,
    password: str | None = None,
    logo_placements: Iterable[LogoPlacement] | None = None,
    output_format: str | None = None,
) -> tuple[bytes, str, str]:
    """Tệp người dùng đính kèm — chỉ sống trong thư mục tạm, không lưu lại."""
    name, data = validate_upload(file_name, file_bytes)
    with tempfile.TemporaryDirectory(prefix="docuvault-upload-") as temp:
        source = Path(temp) / name
        source.write_bytes(data)
        return _process_source(
            source=source,
            logo_bytes=logo_bytes,
            x=x,
            y=y,
            is_watermark=is_watermark,
            password=password,
            logo_placements=logo_placements,
            output_format=output_format,
        )


def _unique_entry_name(candidate: str, taken: Iterable[str]) -> str:
    """Tránh trùng tên trong ZIP (vd. ``a.doc`` và ``a.docx`` cùng ra ``a-logo.docx``)."""
    used = set(taken)
    if candidate not in used:
        return candidate
    path = Path(candidate)
    counter = 2
    while f"{path.stem}-{counter}{path.suffix}" in used:
        counter += 1
    return f"{path.stem}-{counter}{path.suffix}"


def create_output_zip(
    configured_dir: str,
    template_names: list[str],
    logo_bytes: bytes,
    x: float = 0.82,
    y: float = 0.04,
    is_watermark: bool = False,
    password: str | None = None,
    logo_placements: Iterable[LogoPlacement] | None = None,
    uploaded_templates: Iterable[tuple[str | None, bytes]] | None = None,
    output_format: str | None = None,
) -> tuple[bytes, str]:
    """Đóng logo lên nhiều biểu mẫu rồi gói thành 1 ZIP.

    ``template_names`` là biểu mẫu có sẵn trong thư mục cấu hình;
    ``uploaded_templates`` là (tên tệp, nội dung) do người dùng đính kèm.
    """
    validate_logo(logo_bytes)
    normalize_output_format(output_format)
    uploads = list(uploaded_templates or ())
    if not template_names and not uploads:
        raise ValueError("Cần ít nhất một biểu mẫu")
    if len(template_names) != len(set(template_names)):
        raise ValueError("Danh sách biểu mẫu có tên trùng")

    with tempfile.TemporaryDirectory(prefix="docuvault-batch-") as temp:
        work_dir = Path(temp)
        zip_path = work_dir / "processed-forms.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for template_name in template_names:
                output_bytes, output_name, _ = process_template(
                    configured_dir=configured_dir,
                    template_name=template_name,
                    logo_bytes=logo_bytes,
                    x=x,
                    y=y,
                    is_watermark=is_watermark,
                    password=password,
                    logo_placements=logo_placements,
                    output_format=output_format,
                )
                name = _unique_entry_name(output_name, archive.namelist())
                archive.writestr(name, output_bytes)
            for upload_name, upload_bytes in uploads:
                output_bytes, output_name, _ = process_uploaded_template(
                    file_name=upload_name,
                    file_bytes=upload_bytes,
                    logo_bytes=logo_bytes,
                    x=x,
                    y=y,
                    is_watermark=is_watermark,
                    password=password,
                    logo_placements=logo_placements,
                    output_format=output_format,
                )
                name = _unique_entry_name(output_name, archive.namelist())
                archive.writestr(name, output_bytes)
        return zip_path.read_bytes(), zip_path.name


def create_template_preview(configured_dir: str, template_name: str) -> bytes:
    source = resolve_template(configured_dir, template_name)
    if source.suffix.lower() == ".pdf":
        return source.read_bytes()

    with tempfile.TemporaryDirectory(prefix="docuvault-preview-") as temp:
        work_dir = Path(temp)
        docx_source = (
            _convert_doc_to_docx(source, work_dir) if source.suffix.lower() == ".doc" else source
        )
        preview = _convert_to_pdf(docx_source, work_dir)
        return preview.read_bytes()


def _convert_to_pdf(source: Path, work_dir: Path) -> Path:
    """In DOC/DOCX ra PDF bằng LibreOffice headless, trả về path file PDF."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError("Thiết bị chưa cài LibreOffice để tạo preview")
    work_dir.mkdir(parents=True, exist_ok=True)
    profile = work_dir / "lo-profile"
    profile.mkdir(exist_ok=True)
    result = subprocess.run(
        [
            soffice,
            f"-env:UserInstallation=file:///{profile.as_posix()}",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(work_dir),
            str(source),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or "Không thể tạo preview PDF")
    preview = work_dir / f"{source.stem}.pdf"
    if not preview.is_file():
        raise RuntimeError("Không tạo được preview PDF")
    return preview


def _convert_pdf_to_docx(source: Path, work_dir: Path) -> Path:
    """Chuyển PDF sang DOCX bằng service PDF→Word có sẵn của dự án."""
    from app.services import pdf_to_docx_service

    work_dir.mkdir(parents=True, exist_ok=True)
    docx_bytes = pdf_to_docx_service.export_pdf_to_docx(
        source.read_bytes(),
        title=source.stem,
    )
    converted = work_dir / f"{source.stem}.docx"
    converted.write_bytes(docx_bytes)
    return converted


def render_page_png(
    configured_dir: str,
    template_name: str,
    page_number: int = 0,
    zoom: float = 2.0,
) -> tuple[bytes, int, float, float]:
    """Render 1 trang của biểu mẫu thành PNG.

    Trả về (png_bytes, page_count, page_width_pt, page_height_pt) — kích thước
    tính theo point (72 dpi) để frontend suy ra tỉ lệ và đặt logo đúng chỗ.
    """
    source = resolve_template(configured_dir, template_name)
    with tempfile.TemporaryDirectory(prefix="docuvault-pageimg-") as temp:
        return _render_source_page(source, Path(temp), page_number, zoom)


def render_uploaded_page_png(
    file_name: str | None,
    file_bytes: bytes,
    page_number: int = 0,
    zoom: float = 2.0,
) -> tuple[bytes, int, float, float]:
    """Render 1 trang của tệp NGƯỜI DÙNG ĐÍNH KÈM thành PNG (nền kéo thả logo)."""
    name, data = validate_upload(file_name, file_bytes)
    with tempfile.TemporaryDirectory(prefix="docuvault-pageimg-upload-") as temp:
        work_dir = Path(temp)
        source = work_dir / name
        source.write_bytes(data)
        return _render_source_page(source, work_dir, page_number, zoom)


def _render_source_page(
    source: Path,
    work_dir: Path,
    page_number: int,
    zoom: float,
) -> tuple[bytes, int, float, float]:
    """PDF thì render thẳng; DOCX/DOC phải qua LibreOffice in ra PDF trước."""
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        return _render_pdf_page(source, page_number, zoom)
    docx_source = _convert_doc_to_docx(source, work_dir / "convert") if suffix == ".doc" else source
    pdf_path = _convert_to_pdf(docx_source, work_dir / "pdf")
    return _render_pdf_page(pdf_path, page_number, zoom)


def _render_pdf_page(
    pdf_path: Path, page_number: int, zoom: float
) -> tuple[bytes, int, float, float]:
    with pymupdf.open(str(pdf_path)) as document:
        if document.is_encrypted:
            raise ValueError("PDF mẫu đang được bảo vệ bằng mật khẩu")
        if document.page_count == 0:
            raise ValueError("PDF mẫu không có trang")
        if not 0 <= page_number < document.page_count:
            raise ValueError("Số trang không hợp lệ")
        page = document[page_number]
        rect = page.rect
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        png = pix.tobytes("png")
        return png, document.page_count, rect.width, rect.height
