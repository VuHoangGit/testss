"""AI document operations backed by Gemini.

The API key is read only from server configuration. It is never accepted from
the client or returned in an API response.
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


def _request_gemini(parts: list[dict[str, object]]) -> str:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise AIServiceError("AI chưa được cấu hình GEMINI_API_KEY trên backend")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    try:
        response = requests.post(
            url,
            params={"key": settings.gemini_api_key},
            json={"contents": [{"parts": parts}]},
            timeout=settings.gemini_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (401, 403):
            raise AIServiceError("GEMINI_API_KEY không hợp lệ hoặc đã bị thu hồi") from exc
        if status == 404:
            raise AIServiceError(
                f"Không tìm thấy Gemini model '{settings.gemini_model}'"
            ) from exc
        raise AIServiceError("Không kết nối được dịch vụ AI") from exc
    except ValueError as exc:
        raise AIServiceError("Dịch vụ AI trả về dữ liệu không hợp lệ") from exc
    try:
        return str(payload["candidates"][0]["content"]["parts"][0]["text"])
    except (KeyError, IndexError, TypeError) as exc:
        raise AIServiceError("Dịch vụ AI không trả về nội dung") from exc


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
    return _request_gemini(
        [
            {
                "text": (
                    "OCR tài liệu bằng tiếng Việt và tiếng Anh. Giữ thứ tự đọc, tiêu đề "
                    "và xuống dòng. Chỉ trả nội dung."
                )
            },
            {"inline_data": {"mime_type": mime_type, "data": encoded}},
        ]
    ).strip()


def extract_key_values(text: str) -> dict[str, str]:
    raw = _request_gemini(
        [{"text": "Trích xuất các cặp key-value quan trọng. Chỉ trả JSON object:\n" + text[:40000]}]
    )
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIServiceError("AI trả về Key-Value không phải JSON hợp lệ") from exc
    if not isinstance(parsed, Mapping):
        raise AIServiceError("AI trả về Key-Value sai định dạng")
    return {str(key): str(value) for key, value in parsed.items()}


def translate_selection(text: str, target_language: str) -> str:
    return _request_gemini(
        [{"text": f"Dịch chính xác sang {target_language}. Chỉ trả bản dịch:\n{text[:20000]}"}]
    ).strip()


def answer_question(context: str, question: str) -> str:
    return _request_gemini(
        [{
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
