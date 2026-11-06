"""AI document operations backed by an Anthropic-compatible Messages API.

Chạy qua endpoint tương thích Anthropic (vd GLM của z.ai) — cấu hình trong
.env: ANTHROPIC_AUTH_TOKEN / ANTHROPIC_BASE_URL / ANTHROPIC_MODEL. Token chỉ
đọc từ cấu hình server, không bao giờ nhận từ client hay trả về trong response.
"""

import io

import requests
from docx import Document as WordDocument
from pypdf import PdfReader

from app.core.config import get_settings
from app.services import docx_service

# Dòng dài hơn mức này hiếm khi là tiêu đề (dễ là đoạn văn bị ngắt dòng) →
# không nâng thành heading dù cỡ chữ to.
_MAX_HEADING_LINE_CHARS = 200


class AIServiceError(Exception):
    """A configured AI operation could not be completed."""


def post_anthropic(payload: dict[str, object]) -> dict[str, object]:
    """POST payload tuỳ ý tới POST {base_url}/v1/messages, trả JSON đầy đủ.

    Dùng chung cho các tác vụ chỉ cần text (qua request_anthropic) và tác vụ
    cần tool use (voice command) — cùng một chỗ xử lý lỗi/timeout.
    """
    settings = get_settings()
    if not settings.anthropic_auth_token:
        raise AIServiceError("AI is not configured: ANTHROPIC_AUTH_TOKEN is missing on the backend")
    url = f"{settings.anthropic_base_url.rstrip('/')}/v1/messages"
    try:
        response = requests.post(
            url,
            headers={
                "x-api-key": settings.anthropic_auth_token,
                "anthropic-version": "2023-06-01",
            },
            json=payload,
            timeout=settings.anthropic_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        status = getattr(exc.response, "status_code", None)
        detail = _error_message(exc.response)
        # 403 có thể là key hết hạn, hoặc key KHÔNG được cấp quyền model này
        # (z.ai: "key not allowed to access model … models=['mg::text']").
        if status in (401, 403) and "model" in detail.lower():
            model = str(payload.get("model") or settings.anthropic_model)
            raise AIServiceError(
                f"The AI key is not allowed to use model '{model}' "
                f"({detail}). Use a key with access to that model, or change "
                "ANTHROPIC_MODEL / OCR_VISION_MODEL in .env."
            ) from exc
        if status in (401, 403):
            raise AIServiceError(
                "ANTHROPIC_AUTH_TOKEN is invalid or has been revoked"
            ) from exc
        if status == 404:
            raise AIServiceError(
                f"Model '{settings.anthropic_model}' was not found on the AI service"
            ) from exc
        # Model text-only nhận block ảnh → từ chối ngay (GLM: "content.type is
        # invalid, allowed values: ['text']").
        if status == 400 and "image" not in detail.lower() and (
            "content.type is invalid" in detail or "allowed values: ['text']" in detail
        ):
            model = str(payload.get("model") or settings.anthropic_model)
            raise AIServiceError(
                f"Model '{model}' cannot read images (text only), so scanned "
                "pages cannot be OCR'd. Set OCR_VISION_MODEL in .env to a "
                "vision-capable model."
            ) from exc
        raise AIServiceError("Could not connect to the AI service") from exc
    except ValueError as exc:
        raise AIServiceError("The AI service returned invalid data") from exc


def _error_message(response: object) -> str:
    """Lấy `error.message` trong body lỗi của dịch vụ AI ('' nếu không có)."""
    try:
        body = response.json()  # type: ignore[attr-defined]
    except (ValueError, AttributeError):
        return ""
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str):
                return message
    return ""


def request_anthropic(
    content: list[dict[str, object]],
    *,
    system: str | None = None,
    temperature: float | None = None,
    max_tokens: int = 8192,
    model: str | None = None,
) -> str:
    """Gửi 1 lượt user (content blocks) và lấy block text đầu tiên.

    Bỏ qua block "thinking" — model GLM trả kèm block suy luận trước câu trả lời.
    `system` = luật chung (OCR dùng để đặt bộ luật chép tài liệu);
    `temperature=0` = tắt "sáng tạo" cho tác vụ cần chính xác từng con số;
    `model` = ghi đè model cho riêng lượt này (OCR ảnh cần model vision).
    """
    settings = get_settings()
    payload: dict[str, object] = {
        "model": model or settings.anthropic_model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }
    if system:
        payload["system"] = system
    if temperature is not None:
        payload["temperature"] = temperature
    response = post_anthropic(payload)
    try:
        for block in response["content"]:
            if isinstance(block, dict) and block.get("type") == "text":
                return str(block["text"])
    except (KeyError, TypeError) as exc:
        raise AIServiceError("The AI service returned no content") from exc
    raise AIServiceError("The AI service returned no content")


def extract_pdf_pages(data: bytes) -> list[str]:
    """Văn bản lớp text của từng trang PDF (giữ chỉ số trang) — "" nếu trang scan.

    Giữ riêng từng trang để OCR biết trang nào đã có chữ (khỏi gọi AI) và trang
    nào là ảnh scan cần đọc bằng vision.
    """
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise AIServiceError("The PDF is encrypted, remove its password first")
        return [(page.extract_text() or "").strip() for page in reader.pages]
    except AIServiceError:
        raise
    except Exception as exc:
        raise AIServiceError("Could not read the PDF content") from exc


def extract_pdf_text(data: bytes) -> str:
    """Toàn bộ văn bản lớp text của PDF, các trang cách nhau 1 dòng trống."""
    return "\n\n".join(page for page in extract_pdf_pages(data) if page).strip()


def extract_pdf_pages_markdown(data: bytes) -> list[str]:
    """Như [extract_pdf_pages] nhưng giữ cấu trúc: dòng tiêu đề được đánh `#`/`##`.

    `pypdf` trích chữ thuần nên mất hết thông tin cỡ chữ, dẫn tới bản xuất Word
    không có outline level (mục lục rỗng). Ở đây đọc thêm cỡ chữ của từng dòng
    rồi so với cỡ chữ thân văn bản (cỡ phổ biến nhất của cả tài liệu):

    - lớn hơn ≥ 1.7 lần → tiêu đề cấp 1 (`#`)
    - ≥ 1.3 lần → cấp 2 (`##`)
    - ≥ 1.12 lần → cấp 3 (`###`)

    Dùng cho luồng OCR; luồng dịch/tóm tắt vẫn dùng [extract_pdf_pages] để văn
    bản gửi model không bị lẫn dấu Markdown.
    """
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise AIServiceError("The PDF is encrypted, remove its password first")
        page_lines = [_safe_page_lines(page) for page in reader.pages]
        body_size = _body_font_size(page_lines)
        pages: list[str] = []
        for index, lines in enumerate(page_lines):
            if lines:
                pages.append(_lines_to_markdown(lines, body_size))
            else:  # PDF lạ (font/toạ độ hỏng): quay về trích chữ thuần
                pages.append((reader.pages[index].extract_text() or "").strip())
        return pages
    except AIServiceError:
        raise
    except Exception as exc:
        raise AIServiceError("Could not read the PDF content") from exc


def _safe_page_lines(page) -> list[tuple[str, float]]:
    """[(dòng, cỡ chữ lớn nhất trong dòng)]; trang lỗi → [] để đi tiếp."""
    try:
        return _page_lines(page)
    except Exception:  # noqa: BLE001 — pypdf ném nhiều loại lỗi khác nhau
        return []


def _page_lines(page) -> list[tuple[str, float]]:
    """Ghép các mảnh chữ pypdf trả về thành dòng kèm cỡ chữ, đúng thứ tự đọc."""
    lines: list[tuple[str, float]] = []
    parts: list[str] = []
    size = 0.0

    def flush() -> None:
        nonlocal parts, size
        text = "".join(parts).strip()
        if text:
            lines.append((text, size))
        parts = []
        size = 0.0

    def visitor(text: str, cm, tm, font_dict, font_size) -> None:  # noqa: ARG001
        nonlocal size
        chunks = (text or "").split("\n")
        for position, chunk in enumerate(chunks):
            if chunk:
                parts.append(chunk)
                size = max(size, float(font_size or 0))
            if position < len(chunks) - 1:  # pypdf kết thúc mỗi dòng bằng "\n"
                flush()

    page.extract_text(visitor_text=visitor)
    flush()
    return lines


def _body_font_size(page_lines: list[list[tuple[str, float]]]) -> float:
    """Cỡ chữ thân văn bản = cỡ chiếm nhiều ký tự nhất trong cả tài liệu."""
    weights: dict[float, int] = {}
    for lines in page_lines:
        for text, size in lines:
            if size > 0:
                key = round(size, 1)
                weights[key] = weights.get(key, 0) + len(text)
    if not weights:
        return 0.0
    return max(weights.items(), key=lambda item: item[1])[0]


def _lines_to_markdown(lines: list[tuple[str, float]], body_size: float) -> str:
    """Gắn `#`/`##`/`###` cho dòng tiêu đề, còn lại giữ nguyên."""
    output: list[str] = []
    for text, size in lines:
        level = _heading_level(size, body_size) if len(text) <= _MAX_HEADING_LINE_CHARS else 0
        output.append(f"{'#' * level} {text}" if level else text)
    return "\n".join(output)


def _heading_level(size: float, body_size: float) -> int:
    """Cấp tiêu đề suy từ tỉ lệ cỡ chữ (0 = dòng thân văn bản).

    Ngưỡng chọn theo tài liệu thật (thân 10pt): H1 ≈ 18pt (1.8×), H2 ≈ 14pt
    (1.4×), H3 ≈ 12pt (1.2×).
    """
    if size <= 0 or body_size <= 0:
        return 0
    ratio = size / body_size
    if ratio >= 1.7:
        return 1
    if ratio >= 1.3:
        return 2
    if ratio >= 1.12:
        return 3
    return 0


def translate_selection(
    text: str, target_language: str, source_language: str | None = None
) -> str:
    source_hint = (
        f" from {source_language}" if source_language else ""
    )
    return request_anthropic(
        [
            {
                "type": "text",
                "text": (
                    f"Translate accurately{source_hint} into {target_language}. "
                    f"Return the translation only:\n{text[:20000]}"
                ),
            }
        ]
    ).strip()


def answer_question(context: str, question: str) -> str:
    return request_anthropic(
        [{
            "type": "text",
            "text": (
                "You are a document Q&A assistant. Use CONTEXT only. If information is missing, say "
                "that it was not found. Answer in English.\n\n"
                f"CONTEXT:\n{context[:60000]}\n\nCÂU HỎI:\n{question[:4000]}"
            )
        }]
    ).strip()


def make_word_document(text: str, *, title: str | None = None) -> bytes:
    """Xuất văn bản OCR sang .docx **giữ cấu trúc** (heading/outline, bảng, list…).

    Toàn bộ việc parse Markdown nhẹ → style Word nằm ở
    [app.services.docx_service]; hàm này giữ nguyên tên cũ cho nơi gọi.
    """
    return docx_service.to_docx_bytes(text, title=title)


# Loại file đọc được bằng trích xuất text thuần (không cần AI).
_TEXT_MIME_PREFIX = "text/"
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
# Trình duyệt/một số client không nhận diện được đuôi lạ → dò theo tên file.
_TEXT_EXTENSIONS = frozenset({
    ".txt", ".md", ".markdown", ".csv", ".json", ".log", ".xml", ".yml", ".yaml",
    ".py", ".js", ".ts", ".dart", ".java", ".c", ".cpp", ".html", ".css", ".ini",
})


def is_text_extractable(mime_type: str, name: str = "") -> bool:
    """True nếu [extract_document_text] xử lý được loại file này."""
    return (
        mime_type in ("application/pdf", _DOCX_MIME)
        or mime_type.startswith(_TEXT_MIME_PREFIX)
        or name.lower().endswith(tuple(_TEXT_EXTENSIONS))
    )


def extract_document_text(data: bytes, mime_type: str, name: str = "") -> str:
    """Trích văn bản thô từ tài liệu: PDF (pypdf), Word (python-docx),
    các loại text (txt/md/csv/code...) — giải mã utf-8.

    Trả "" nếu không trích được ký tự nào. Ném AIServiceError khi file mã hóa
    hoặc định dạng không hỗ trợ (ảnh_scan cần dùng OCR riêng).
    """
    if not is_text_extractable(mime_type, name):
        raise AIServiceError(
            "This file type cannot be read (supported: PDF, Word, txt/md and plain text)"
        )
    if mime_type == "application/pdf":
        return extract_pdf_text(data)
    if mime_type == _DOCX_MIME:
        try:
            document = WordDocument(io.BytesIO(data))
            return "\n\n".join(
                paragraph.text for paragraph in document.paragraphs if paragraph.text
            ).strip()
        except AIServiceError:
            raise
        except Exception as exc:
            raise AIServiceError("Could not read the Word file content") from exc
    try:
        return data.decode("utf-8", errors="replace").strip()
    except Exception as exc:  # hiếm: decode với replace gần như không fail
        raise AIServiceError("Could not read the text file content") from exc
