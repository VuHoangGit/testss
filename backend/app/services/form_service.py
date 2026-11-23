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
) -> tuple[bytes, str, str]:
    """Trả (bytes, tên file, MIME) sau khi tự xóa toàn bộ thư mục tạm."""
    logo_bytes, _ = validate_logo(logo_bytes)
    source = resolve_template(configured_dir, template_name)

    with tempfile.TemporaryDirectory(prefix="docuvault-logo-") as temp:
        work_dir = Path(temp)
        if source.suffix.lower() == ".pdf":
            output = work_dir / f"{source.stem}-logo.pdf"
            _add_logo_to_pdf(
                source,
                logo_bytes,
                output,
                x=x,
                y=y,
                is_watermark=is_watermark,
                password=password,
                logo_placements=logo_placements,
            )
            return output.read_bytes(), output.name, "application/pdf"

        if source.suffix.lower() == ".doc":
            docx_source = _convert_doc_to_docx(source, work_dir)
            output = work_dir / f"{source.stem}-logo.docx"
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
        return (
            output.read_bytes(),
            output.name,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )


def create_output_zip(
    configured_dir: str,
    template_names: list[str],
    logo_bytes: bytes,
    x: float = 0.82,
    y: float = 0.04,
    is_watermark: bool = False,
    password: str | None = None,
    logo_placements: Iterable[LogoPlacement] | None = None,
) -> tuple[bytes, str]:
    validate_logo(logo_bytes)
    if not template_names:
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
                )
                archive.writestr(output_name, output_bytes)
        return zip_path.read_bytes(), zip_path.name


def create_template_preview(configured_dir: str, template_name: str) -> bytes:
    source = resolve_template(configured_dir, template_name)
    if source.suffix.lower() == ".pdf":
        return source.read_bytes()

    with tempfile.TemporaryDirectory(prefix="docuvault-preview-") as temp:
        work_dir = Path(temp)
        docx_source = (
            _convert_doc_to_docx(source, work_dir)
            if source.suffix.lower() == ".doc"
            else source
        )
        preview = _docx_to_pdf(docx_source, work_dir)
        return preview.read_bytes()


def _docx_to_pdf(docx_source: Path, work_dir: Path) -> Path:
    """Chuyển DOCX sang PDF bằng LibreOffice headless, trả về path file PDF."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError("Thiết bị chưa cài LibreOffice để tạo preview")
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
            str(docx_source),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or "Không thể tạo preview PDF")
    preview = work_dir / f"{docx_source.stem}.pdf"
    if not preview.is_file():
        raise RuntimeError("Không tạo được preview PDF")
    return preview


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
    suffix = source.suffix.lower()
    if suffix == ".pdf":
        pdf_path = source
    else:
        with tempfile.TemporaryDirectory(prefix="docuvault-pageimg-") as temp:
            work_dir = Path(temp)
            docx_source = (
                _convert_doc_to_docx(source, work_dir)
                if suffix == ".doc"
                else source
            )
            pdf_path = _docx_to_pdf(docx_source, work_dir)
            return _render_pdf_page(pdf_path, page_number, zoom)

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
