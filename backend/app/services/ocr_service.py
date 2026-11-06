"""OCR chuyên nghiệp: prompt 3 tầng, mỗi trang một lượt gọi, temperature = 0.

Nguyên tắc (xem docs/ocr-pipeline.md):

- **PDF có lớp text** → dùng luôn văn bản trích được, không gọi AI (nhanh,
  chính xác, không tốn credit).
- **Trang scan / ảnh chụp** → render ra ảnh (~200 DPI, cạnh dài ≤ 2000px) rồi
  gửi AI đọc. Mỗi lượt chỉ gửi **một trang**: biết sai ở trang nào, retry riêng
  trang lỗi, trang hỏng không làm hỏng cả tài liệu.
- **temperature = 0** cho mọi lượt gọi: model không được "sáng tạo" số liệu.
- **Luật OCR (tầng 1)** là system prompt: chỉ chép thấy gì ghi nấy, không suy
  đoán, không tự sửa số tiền / ngày tháng, chỗ không đọc được ghi [?].
- **Trích xuất có cấu trúc (tầng 3)** dùng JSON schema CỐ ĐỊNH — khoá không đổi
  giữa các lần chạy nên code phía sau dùng được.
- **Hậu kiểm bằng máy**: regex kiểm ngày tháng / số tiền / số giấy tờ, đối
  chiếu tổng tiền với nội dung, gom cảnh báo cho người dùng đối soát.
"""

import base64
import io
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings
from app.services import ai_service

# ---------------------------------------------------------------------------
# Tầng 1 — system prompt dùng chung cho mọi trang. Đây là phần quyết định phần
# lớn chất lượng: luật 2 (không đổi định dạng số liệu), luật 3 (đánh dấu chỗ
# không đọc được) và luật 10 (cấm bịa) ngăn kiểu lỗi nguy hiểm nhất — model tự
# điền số tiền / ngày tháng sai mà nhìn qua không phát hiện được.

_OCR_RULES = [
    "Bạn là chuyên viên số hoá tài liệu. Nhiệm vụ: chép lại chính xác nội dung "
    "nhìn thấy trong ảnh trang tài liệu.",
    "",
    "LUẬT BẮT BUỘC:",
    "1. Chỉ ghi những gì nhìn thấy. Không suy đoán, không bổ sung, không tự sửa "
    'lỗi chính tả, không "làm đẹp" câu chữ.',
    "2. Giữ nguyên y hệt: số tiền, ngày tháng, số hợp đồng, mã số thuế, số CCCD, "
    "đơn vị đo, dấu câu. Không đổi định dạng (31/12/2025 KHÔNG thành "
    "December 31, 2025).",
    "3. Ký tự hoặc từ không đọc được: ghi [?]. Đoạn chắc chắn bị mất: ghi [mất chữ].",
    "4. Bảng: xuất Markdown table, giữ đúng số cột và thứ tự cột. Ô trống để "
    "trống. Không gộp ô, không tự thêm cột, không tính toán thêm.",
    "5. Văn bản nhiều cột: đọc hết cột trái từ trên xuống, rồi mới sang cột phải. "
    "Không trộn dòng giữa các cột.",
    "6. Tiêu đề lớn nhất của tài liệu (tên chương/phần) ghi bằng #, mục con "
    "bằng ##, mục nhỏ hơn nữa bằng ###. Dòng không phải tiêu đề thì không "
    "đánh dấu.",
    "7. Chữ ký tay / con dấu / hình ảnh: ghi chú ngắn trong ngoặc vuông, ví dụ "
    "[chữ ký tay], [dấu đỏ tròn].",
    "8. Trang trắng hoặc không có chữ: trả đúng một dòng "
    "[trang không có nội dung chữ].",
    "9. Không thêm lời mở đầu, kết luận, giải thích. Không bọc trong ```.",
    "10. Ảnh mờ/thiếu thì vẫn chép phần đọc được — TUYỆT ĐỐI không bịa để lấp "
    "chỗ trống.",
]
OCR_SYSTEM_PROMPT = "\n".join(_OCR_RULES)

# Tầng 2 — mẫu user prompt gửi kèm từng trang.
PAGE_PROMPT_TEMPLATE = """Trang {page}/{total} của tài liệu.
Loại tài liệu: {doc_type}
Ngôn ngữ chính: {language}
{glossary}Hãy chép lại toàn bộ nội dung trang này theo đúng luật đã nêu."""

# Tầng 3 — trích xuất có cấu trúc theo schema cố định (khoá không đổi).
EXTRACTION_SYSTEM_PROMPT = (
    "Bạn trích xuất dữ liệu từ văn bản đã OCR. Chỉ trả về đúng một JSON object "
    "theo schema được yêu cầu, không thêm khoá lạ, không giải thích, không bọc "
    "trong ```. Không có thông tin thì để null — TUYỆT ĐỐI không suy đoán hay "
    "tự tính toán. Trường nào không chắc chắn thì ghi tên trường đó vào "
    "truong_khong_chac_chan."
)

EXTRACTION_PROMPT = """Từ nội dung OCR dưới đây, trích xuất theo đúng JSON sau.
Không thêm khoá lạ. Không có thông tin thì để null. Chỉ trả JSON, không giải thích.

{
  "loai_tai_lieu": null,
  "so_hieu": null,
  "ngay_ban_hanh": null,
  "cac_ben": [{"vai_tro": null, "ten": null, "ma_so": null}],
  "tong_tien": {"so": null, "don_vi": "VND"},
  "thoi_han": null,
  "dieu_khoan_chinh": [],
  "truong_khong_chac_chan": []
}

NỘI DUNG OCR:
__TEXT__"""

# Khoá của schema cố định — đổi ở đây là đổi hợp đồng dữ liệu với client.
STRUCTURED_FIELDS = (
    "loai_tai_lieu",
    "so_hieu",
    "ngay_ban_hanh",
    "cac_ben",
    "tong_tien",
    "thoi_han",
    "dieu_khoan_chinh",
    "truong_khong_chac_chan",
)

EMPTY_PAGE_MARKER = "[trang không có nội dung chữ]"
UNREADABLE_MARKER = "[?]"
LOST_TEXT_MARKER = "[mất chữ]"

# Ảnh gửi AI: ~200 DPI (PDF mặc định 72 DPI), cạnh dài ≤ 2000px — nhỏ hơn thì
# mất chữ nhỏ và dấu tiếng Việt, lớn hơn thì vô ích và tốn token.
_MAX_LONG_SIDE = 2000
# Vượt ngưỡng này thì nén JPEG cho nhẹ request (vẫn giữ nét chữ ở quality 90).
_MAX_IMAGE_BYTES = 4 * 1024 * 1024

_IMAGE_MIME_TYPES = frozenset({"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"})

# Hậu kiểm bằng máy — không tin model tuyệt đối.
_DATE_RE = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\b")
_MONEY_RE = re.compile(r"(\d[\d.,]*)\s*(?:VN[DĐ]|₫|đồng|dong)\b", re.IGNORECASE)
_DIGITS_RE = re.compile(r"\d+")
_UNCERTAIN_MARKERS = (UNREADABLE_MARKER, LOST_TEXT_MARKER)


@dataclass(frozen=True)
class OcrOptions:
    """Tuỳ chọn cho một lượt OCR (client có thể truyền, không bắt buộc)."""

    doc_type: str = "tự nhận diện"
    language: str = "tiếng Việt, tiếng Anh hoặc song ngữ"
    # Tên công ty / mã sản phẩm / tên riêng — chỉ để nhận dạng đúng chữ,
    # model không được thêm vào nội dung.
    glossary: str = ""
    max_pages: int = 20
    dpi: int = 200


@dataclass(frozen=True)
class OcrPage:
    """Kết quả của một trang. `source` = "text-layer" hoặc "vision"."""

    page: int
    text: str
    source: str


@dataclass(frozen=True)
class OcrOutcome:
    """Toàn bộ kết quả OCR: từng trang, dữ liệu có cấu trúc, cảnh báo hậu kiểm."""

    pages: list[OcrPage] = field(default_factory=list)
    structured: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Toàn bộ nội dung; nhiều trang thì chèn mốc `--- Trang N ---`.

        Tài liệu 1 trang giữ nguyên văn bản (không thêm mốc) để bản xuất Word
        và chức năng đọc lại không bị nhiễu.
        """
        if len(self.pages) <= 1:
            return "\n\n".join(page.text for page in self.pages).strip()
        return "\n\n".join(
            f"--- Trang {page.page} ---\n{page.text}".rstrip() for page in self.pages
        ).strip()

    @property
    def key_values(self) -> dict[str, str]:
        """Dạng phẳng của [structured] (giữ hợp đồng cũ với client)."""
        return flatten_structured(self.structured)


def _settings_defaults() -> tuple[int, int]:
    settings = get_settings()
    return settings.ocr_max_pages, settings.ocr_dpi


def default_options() -> OcrOptions:
    """Tuỳ chọn mặc định lấy từ cấu hình server (.env)."""
    max_pages, dpi = _settings_defaults()
    return OcrOptions(max_pages=max_pages, dpi=dpi)


# ---------------------------------------------------------------------------
# Prompt


def build_page_prompt(page: int, total: int, options: OcrOptions) -> str:
    """Sinh user prompt cho một trang (tầng 2) — gửi kèm ảnh của đúng trang đó."""
    glossary = (options.glossary or "").strip()
    glossary_line = (
        f"Thuật ngữ riêng cần nhận đúng: {glossary}\n"
        "(chỉ để nhận dạng đúng chữ — không được thêm vào nội dung)\n"
        if glossary
        else ""
    )
    return PAGE_PROMPT_TEMPLATE.format(
        page=page,
        total=total,
        doc_type=options.doc_type or "tự nhận diện",
        language=options.language or "tự nhận diện",
        glossary=glossary_line,
    )


# ---------------------------------------------------------------------------
# Gọi AI


def vision_model() -> str | None:
    """Model đọc ảnh cho OCR (OCR_VISION_MODEL); None = dùng model mặc định.

    Cần đặt riêng khi model văn bản của dịch vụ AI không nhận block ảnh.
    """
    configured = (get_settings().ocr_vision_model or "").strip()
    return configured or None


def _read_page_with_vision(png: bytes, media_type: str, prompt: str) -> str:
    """Gửi 1 ảnh trang cho model đọc, temperature = 0."""
    encoded = base64.b64encode(png).decode("ascii")
    return ai_service.request_anthropic(
        [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": encoded},
            },
            {"type": "text", "text": prompt},
        ],
        system=OCR_SYSTEM_PROMPT,
        temperature=0.0,
        model=vision_model(),
    ).strip()



def _render_pdf_pages(
    data: bytes, indexes: Sequence[int], dpi: int
) -> dict[int, tuple[bytes, str]]:
    """Render các trang cần OCR thành ảnh, trả {index: (bytes, media_type)}."""
    try:
        import pypdfium2 as pdfium
        from PIL import Image
    except ImportError as exc:  # thiếu package native
        raise ai_service.AIServiceError(
            "The server is missing the PDF rendering library (pypdfium2/Pillow). "
            "Run: pip install -r requirements.txt"
        ) from exc

    rendered: dict[int, tuple[bytes, str]] = {}
    document = pdfium.PdfDocument(data)
    try:
        for index in indexes:
            page = document[index]
            bitmap = page.render(scale=max(72, dpi) / 72)
            try:
                image = bitmap.to_pil().convert("RGB")
            finally:
                bitmap.close()
            if max(image.size) > _MAX_LONG_SIDE:
                image.thumbnail((_MAX_LONG_SIDE, _MAX_LONG_SIDE), Image.Resampling.LANCZOS)
            rendered[index] = _encode_image(image)
    except ai_service.AIServiceError:
        raise
    except Exception as exc:  # noqa: BLE001 — pdfium ném nhiều loại lỗi khác nhau
        raise ai_service.AIServiceError("Could not render the PDF page for OCR") from exc
    finally:
        document.close()
    return rendered


def _encode_image(image) -> tuple[bytes, str]:
    """PNG cho nét chữ; quá nặng thì chuyển JPEG để không vượt giới hạn request."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    payload = buffer.getvalue()
    if len(payload) <= _MAX_IMAGE_BYTES:
        return payload, "image/png"
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90, optimize=True)
    return buffer.getvalue(), "image/jpeg"


# ---------------------------------------------------------------------------
# Luồng chính


def ocr_document_bytes(
    data: bytes,
    mime_type: str,
    name: str = "",
    options: OcrOptions | None = None,
) -> OcrOutcome:
    """OCR tài liệu (PDF hoặc ảnh) → [OcrOutcome].

    Ném [ai_service.AIServiceError] khi không đọc được gì để phía API hoàn
    credit cho người dùng.
    """
    options = options or default_options()
    if mime_type == "application/pdf":
        pages, warnings = _ocr_pdf(data, options)
    elif mime_type in _IMAGE_MIME_TYPES:
        pages, warnings = _ocr_image(data, mime_type, options, name=name)
    else:
        raise ai_service.AIServiceError(
            f"Cannot OCR \"{mime_type or name}\". Supported: PDF and images "
            "(png/jpeg/webp/gif)."
        )

    text = OcrOutcome(pages=pages).text
    if pages and all(page.text.strip() == EMPTY_PAGE_MARKER for page in pages):
        # Không có chữ nào → khỏi tốn 1 lượt gọi AI để trích trường dữ liệu
        structured, structure_warnings = empty_structured(), [
            "No readable text was found on any page — nothing to extract."
        ]
    else:
        structured, structure_warnings = extract_structured(text)
    warnings.extend(structure_warnings)
    warnings.extend(post_checks(text, structured))
    return OcrOutcome(pages=pages, structured=structured, warnings=_dedupe(warnings))


def _ocr_pdf(data: bytes, options: OcrOptions) -> tuple[list[OcrPage], list[str]]:
    """OCR từng trang PDF: trang có lớp text dùng luôn, trang scan gửi ảnh."""
    warnings: list[str] = []
    # Bản có cấu trúc (`#` cho tiêu đề) để file Word xuất ra giữ được outline.
    page_texts = ai_service.extract_pdf_pages_markdown(data)
    total = len(page_texts)
    if total == 0:
        raise ai_service.AIServiceError("The PDF has no pages to OCR")

    limit = min(total, max(1, options.max_pages))
    if limit < total:
        warnings.append(
            f"The document has {total} pages; only the first {limit} were processed "
            "(OCR_MAX_PAGES limit)."
        )

    vision_indexes = [index for index in range(limit) if not page_texts[index].strip()]
    # Render lỗi thì vẫn cố đi tiếp: trang nào hỏng chỉ báo trang đó.
    rendered: dict[int, tuple[bytes, str]] = {}
    if vision_indexes:
        try:
            rendered = _render_pdf_pages(data, vision_indexes, options.dpi)
        except ai_service.AIServiceError as exc:
            warnings.append(f"Could not render the scanned pages ({exc}).")

    pages: list[OcrPage] = []
    vision_failures = 0
    last_failure = ""
    for index in range(limit):
        number = index + 1
        page_text = page_texts[index].strip()
        if page_text:
            pages.append(OcrPage(page=number, text=page_text, source="text-layer"))
            continue
        image = rendered.get(index)
        if image is None:
            vision_failures += 1
            warnings.append(f"Page {number}: could not render an image to OCR.")
            pages.append(OcrPage(page=number, text=EMPTY_PAGE_MARKER, source="vision"))
            continue
        try:
            text = _read_page_with_vision(
                image[0], image[1], build_page_prompt(number, limit, options)
            )
        except ai_service.AIServiceError as exc:
            vision_failures += 1
            last_failure = str(exc)
            warnings.append(f"Page {number}: could not be read ({exc}).")
            pages.append(OcrPage(page=number, text=EMPTY_PAGE_MARKER, source="vision"))
            continue
        pages.append(OcrPage(page=number, text=text or EMPTY_PAGE_MARKER, source="vision"))

    if vision_failures and vision_failures == len(vision_indexes) and not any(
        page.source == "text-layer" for page in pages
    ):
        raise ai_service.AIServiceError(
            "No page of the document could be read"
            + (f": {last_failure}" if last_failure else ". Try again or check the file.")
        )
    return pages, warnings


def _ocr_image(
    data: bytes, mime_type: str, options: OcrOptions, *, name: str = ""
) -> tuple[list[OcrPage], list[str]]:
    """OCR một ảnh đơn (ảnh chụp / ảnh scan) — coi như tài liệu 1 trang."""
    media_type = "image/jpeg" if mime_type == "image/jpg" else mime_type
    try:
        text = _read_page_with_vision(
            data, media_type, build_page_prompt(1, 1, options)
        )
    except ai_service.AIServiceError as exc:
        label = name or "tài liệu"
        raise ai_service.AIServiceError(f"Could not read the image '{label}': {exc}") from exc
    return [OcrPage(page=1, text=text or EMPTY_PAGE_MARKER, source="vision")], []


# ---------------------------------------------------------------------------
# Tầng 3 — trích xuất có cấu trúc


def empty_structured() -> dict[str, Any]:
    """Schema rỗng — dùng khi không trích được gì (khoá vẫn đủ, giá trị null)."""
    return {
        "loai_tai_lieu": None,
        "so_hieu": None,
        "ngay_ban_hanh": None,
        "cac_ben": [],
        "tong_tien": {"so": None, "don_vi": "VND"},
        "thoi_han": None,
        "dieu_khoan_chinh": [],
        "truong_khong_chac_chan": [],
    }


def extract_structured(text: str) -> tuple[dict[str, Any], list[str]]:
    """Trích dữ liệu theo schema cố định; lỗi → schema rỗng + cảnh báo.

    Không ném lỗi vì phần văn bản OCR vẫn có giá trị cho người dùng.
    """
    if not text.strip():
        return empty_structured(), ["No text content, so no fields could be extracted."]
    raw = ai_service.request_anthropic(
        # Prompt chứa JSON schema ({...}) nên thay chuỗi thay vì str.format
        [{"type": "text", "text": EXTRACTION_PROMPT.replace("__TEXT__", text[:40000])}],
        system=EXTRACTION_SYSTEM_PROMPT,
        temperature=0.0,
    )
    parsed = _load_json_object(raw)
    if parsed is None:
        return empty_structured(), [
            "The AI returned field data that is not valid JSON — fields were skipped. "
            "Read the text or run OCR again."
        ]
    struct_warnings = [
        f"The AI is unsure about: {item}"
        for item in _as_string_list(parsed.get("truong_khong_chac_chan"))
    ]
    return normalize_structured(parsed), struct_warnings


def _load_json_object(raw: str) -> dict[str, Any] | None:
    """Bóc JSON object khỏi câu trả lời (bỏ ``` và lời dẫn nếu có)."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def normalize_structured(raw: dict[str, Any]) -> dict[str, Any]:
    """Ép kết quả model về đúng schema: đủ khoá, sai kiểu → null."""
    result = empty_structured()
    for key in ("loai_tai_lieu", "so_hieu", "ngay_ban_hanh", "thoi_han"):
        value = _as_text(raw.get(key))
        if value:
            result[key] = value

    parties: list[dict[str, Any]] = []
    for item in raw.get("cac_ben") or []:
        if not isinstance(item, dict):
            continue
        party = {
            "vai_tro": _as_text(item.get("vai_tro")),
            "ten": _as_text(item.get("ten")),
            "ma_so": _as_text(item.get("ma_so")),
        }
        if any(party.values()):
            parties.append(party)
    result["cac_ben"] = parties

    money = raw.get("tong_tien")
    if isinstance(money, dict):
        result["tong_tien"] = {
            "so": _as_text(money.get("so")),
            "don_vi": _as_text(money.get("don_vi")) or "VND",
        }
    elif money is not None:
        result["tong_tien"] = {"so": _as_text(money), "don_vi": "VND"}

    result["dieu_khoan_chinh"] = _as_string_list(raw.get("dieu_khoan_chinh"))
    result["truong_khong_chac_chan"] = _as_string_list(raw.get("truong_khong_chac_chan"))
    return result


def _as_text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, int | float):
        # Số tiền lớn: in dạng số nguyên, không dùng float để khỏi mất chữ số
        return str(int(value)) if float(value).is_integer() else str(value)
    return None


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = _as_text(item)
        if text:
            items.append(text)
    return items


def flatten_structured(structured: dict[str, Any]) -> dict[str, str]:
    """Chuyển schema sang dict phẳng `khoá → chuỗi` cho UI key-value."""
    flat: dict[str, str] = {}
    for key in STRUCTURED_FIELDS:
        value = structured.get(key)
        if key == "cac_ben" and isinstance(value, list):
            parts = [
                " – ".join(
                    part
                    for part in (
                        _as_text(item.get("vai_tro")),
                        _as_text(item.get("ten")),
                        _as_text(item.get("ma_so")),
                    )
                    if part
                )
                for item in value
                if isinstance(item, dict)
            ]
            joined = "; ".join(part for part in parts if part)
            if joined:
                flat[key] = joined
        elif key == "tong_tien" and isinstance(value, dict):
            amount = _as_text(value.get("so"))
            if amount:
                unit = _as_text(value.get("don_vi")) or "VND"
                flat[key] = f"{amount} {unit}".strip()
        elif isinstance(value, list):
            joined = "; ".join(item for item in value if isinstance(item, str) and item)
            if joined:
                flat[key] = joined
        elif isinstance(value, str) and value:
            flat[key] = value
    return flat


# ---------------------------------------------------------------------------
# Hậu kiểm bằng máy


def post_checks(text: str, structured: dict[str, Any]) -> list[str]:
    """Kiểm tra máy những chỗ model hay sai — trả danh sách cảnh báo tiếng Việt."""
    warnings: list[str] = []

    uncertain = sum(text.count(marker) for marker in _UNCERTAIN_MARKERS)
    if uncertain:
        warnings.append(
            f"{uncertain} spot(s) marked as unreadable ([?]/[lost text]) — "
            "check them against the original page."
        )

    invalid_dates = [
        match.group(0)
        for match in _DATE_RE.finditer(text)
        if not _is_valid_date(match.group(1), match.group(2), match.group(3))
    ]
    if invalid_dates:
        warnings.append(
            "Suspicious date format: " + ", ".join(sorted(set(invalid_dates))[:5])
        )

    money_values = [_normalize_digits(match.group(1)) for match in _MONEY_RE.finditer(text)]
    if any(len(value) > 12 for value in money_values):
        warnings.append("Unusually long amount found — check it by eye.")

    digits_in_text = _normalize_digits(text)
    amount = _as_text((structured.get("tong_tien") or {}).get("so"))
    if amount:
        if _normalize_digits(amount) not in digits_in_text:
            warnings.append(
                f"The total the AI extracted ({amount}) does not appear verbatim in the "
                "content — verify it."
            )
        elif len(_normalize_digits(amount)) < 4:
            warnings.append(f"The total the AI extracted ({amount}) looks too short — verify it.")

    for party in structured.get("cac_ben") or []:
        if not isinstance(party, dict):
            continue
        code = _as_text(party.get("ma_so"))
        if code and code.isdigit() and len(code) not in (9, 10, 12, 13):
            warnings.append(
                f"The code '{code}' does not look like a national ID (9/12 digits) or a tax "
                "code (10/13 digits) — verify it."
            )

    if text.strip() == EMPTY_PAGE_MARKER:
        warnings.append(
            "The AI found no text content — if this is a scan, check the page image."
        )
    return warnings


def _is_valid_date(day: str, month: str, year: str) -> bool:
    day_value, month_value = int(day), int(month)
    if not 1 <= month_value <= 12 or not 1 <= day_value <= 31:
        return False
    return len(year) in (2, 4)


def _normalize_digits(value: str) -> str:
    return "".join(_DIGITS_RE.findall(value))


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
