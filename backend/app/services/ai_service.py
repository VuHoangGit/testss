"""AI document operations backed by an Anthropic-compatible Messages API.

Chạy qua endpoint tương thích Anthropic (vd GLM của z.ai) — cấu hình trong
.env: ANTHROPIC_AUTH_TOKEN / ANTHROPIC_BASE_URL / ANTHROPIC_MODEL. Token chỉ
đọc từ cấu hình server, không bao giờ nhận từ client hay trả về trong response.
"""

import base64
import io
import json
from collections.abc import Mapping

import requests
from docx import Document as WordDocument
from pypdf import PdfReader

from app.core.config import get_settings


class AIServiceError(Exception):
    """A configured AI operation could not be completed."""


def post_anthropic(payload: dict[str, object]) -> dict[str, object]:
    """POST payload tuỳ ý tới POST {base_url}/v1/messages, trả JSON đầy đủ.

    Dùng chung cho các tác vụ chỉ cần text (qua _request_anthropic) và tác vụ
    cần tool use (voice command) — cùng một chỗ xử lý lỗi/timeout.
    """
    settings = get_settings()
    if not settings.anthropic_auth_token:
        raise AIServiceError("AI chưa được cấu hình ANTHROPIC_AUTH_TOKEN trên backend")
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
        if status in (401, 403):
            raise AIServiceError(
                "ANTHROPIC_AUTH_TOKEN không hợp lệ hoặc đã bị thu hồi"
            ) from exc
        if status == 404:
            raise AIServiceError(
                f"Không tìm thấy model '{settings.anthropic_model}' trên dịch vụ AI"
            ) from exc
        raise AIServiceError("Không kết nối được dịch vụ AI") from exc
    except ValueError as exc:
        raise AIServiceError("Dịch vụ AI trả về dữ liệu không hợp lệ") from exc


def _request_anthropic(content: list[dict[str, object]]) -> str:
    """Gửi 1 lượt user (content blocks) và lấy block text đầu tiên.

    Bỏ qua block "thinking" — model GLM trả kèm block suy luận trước câu trả lời.
    """
    settings = get_settings()
    payload: dict[str, object] = {
        "model": settings.anthropic_model,
        "max_tokens": 8192,
        "messages": [{"role": "user", "content": content}],
    }
    response = post_anthropic(payload)
    try:
        for block in response["content"]:
            if isinstance(block, dict) and block.get("type") == "text":
                return str(block["text"])
    except (KeyError, TypeError) as exc:
        raise AIServiceError("Dịch vụ AI không trả về nội dung") from exc
    raise AIServiceError("Dịch vụ AI không trả về nội dung")


def extract_pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise AIServiceError("PDF đang được mã hóa, hãy gỡ mật khẩu trước")
        return "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except AIServiceError:
        raise
    except Exception as exc:
        raise AIServiceError("Không đọc được nội dung PDF") from exc


def ocr_document(data: bytes, mime_type: str) -> str:
    if mime_type == "application/pdf":
        text = extract_pdf_text(data)
        if text:
            return text
    encoded = base64.b64encode(data).decode("ascii")
    return _request_anthropic(
        [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": mime_type, "data": encoded},
            },
            {
                "type": "text",
                "text": (
                    "OCR tài liệu bằng tiếng Việt và tiếng Anh. Giữ thứ tự đọc, tiêu đề "
                    "và xuống dòng. Chỉ trả nội dung."
                )
            },
        ]
    ).strip()


def extract_key_values(text: str) -> dict[str, str]:
    raw = _request_anthropic(
        [
            {
                "type": "text",
                "text": "Trích xuất các cặp key-value quan trọng. Chỉ trả JSON object:\n"
                + text[:40000],
            }
        ]
    ).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIServiceError("AI trả về Key-Value không phải JSON hợp lệ") from exc
    if not isinstance(parsed, Mapping):
        raise AIServiceError("AI trả về Key-Value sai định dạng")
    return {str(key): str(value) for key, value in parsed.items()}


def translate_selection(
    text: str, target_language: str, source_language: str | None = None
) -> str:
    source_hint = (
        f" từ {source_language}" if source_language else ""
    )
    return _request_anthropic(
        [
            {
                "type": "text",
                "text": (
                    f"Dịch chính xác{source_hint} sang {target_language}. "
                    f"Chỉ trả bản dịch:\n{text[:20000]}"
                ),
            }
        ]
    ).strip()


def answer_question(context: str, question: str) -> str:
    return _request_anthropic(
        [{
            "type": "text",
            "text": (
                "Bạn là trợ lý hỏi đáp tài liệu. Chỉ dùng CONTEXT. Nếu thiếu thông tin, nói rõ "
                "không tìm thấy. Trả lời bằng tiếng Việt.\n\n"
                f"CONTEXT:\n{context[:60000]}\n\nCÂU HỎI:\n{question[:4000]}"
            )
        }]
    ).strip()


def make_word_document(text: str) -> bytes:
    document = WordDocument()
    for paragraph in text.splitlines() or [""]:
        document.add_paragraph(paragraph)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


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
            "Chưa hỗ trợ đọc loại file này (hỗ trợ PDF, Word, txt/md và file văn bản)"
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
            raise AIServiceError("Không đọc được nội dung file Word") from exc
    try:
        return data.decode("utf-8", errors="replace").strip()
    except Exception as exc:  # hiếm: decode với replace gần như không fail
        raise AIServiceError("Không đọc được nội dung file văn bản") from exc
