"""Test map lỗi dịch vụ AI + chọn model vision cho OCR ảnh."""

import pytest
import requests

from app.core.config import get_settings
from app.services import ai_service, ocr_service


class _FakeResponse:
    """Giả response requests: raise_for_status nổ, json() trả body lỗi."""

    def __init__(self, status_code: int, body: dict | None = None) -> None:
        self.status_code = status_code
        self._body = body or {}

    def raise_for_status(self) -> None:
        raise requests.HTTPError(response=self)

    def json(self) -> dict:
        return self._body


def _http_error(response: _FakeResponse) -> requests.HTTPError:
    error = requests.HTTPError(response=response)
    return error


def test_key_without_model_access_gets_actionable_message(monkeypatch):
    """z.ai: key chỉ có nhóm mg::text gọi model vision → 403."""
    body = {
        "error": {
            "message": "key not allowed to access model. This key can only access "
            "models=['mg::text']. Tried to access glm-4.6v",
            "code": "key_model_access_denied",
        }
    }

    def fake_post(url, headers=None, json=None, timeout=None):
        raise requests.HTTPError(response=_FakeResponse(403, body))

    monkeypatch.setattr(ai_service.requests, "post", fake_post)

    with pytest.raises(ai_service.AIServiceError) as error:
        ai_service.request_anthropic(
            [{"type": "text", "text": "xin chào"}], model="glm-4.6v"
        )

    message = str(error.value)
    assert "glm-4.6v" in message
    assert "OCR_VISION_MODEL" in message


def test_text_only_model_rejects_image_blocks(monkeypatch):
    body = {
        "error": {
            "message": "messages.content.type is invalid, allowed values: ['text']"
        }
    }

    def fake_post(url, headers=None, json=None, timeout=None):
        raise requests.HTTPError(response=_FakeResponse(400, body))

    monkeypatch.setattr(ai_service.requests, "post", fake_post)

    with pytest.raises(ai_service.AIServiceError) as error:
        ocr_service._read_page_with_vision(b"png", "image/png", "prompt")

    message = str(error.value)
    assert "cannot read images" in message
    assert "OCR_VISION_MODEL" in message


def test_invalid_token_keeps_original_message(monkeypatch):
    body = {"error": {"message": "invalid api key"}}

    def fake_post(url, headers=None, json=None, timeout=None):
        raise requests.HTTPError(response=_FakeResponse(401, body))

    monkeypatch.setattr(ai_service.requests, "post", fake_post)

    with pytest.raises(ai_service.AIServiceError) as error:
        ai_service.request_anthropic([{"type": "text", "text": "xin chào"}])

    assert "ANTHROPIC_AUTH_TOKEN is invalid" in str(error.value)


def test_vision_model_setting_is_used_for_image_pages(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ocr_vision_model", "glm-4.6v")
    captured: dict[str, object] = {}

    def fake_post(payload):
        captured.update(payload)
        return {"content": [{"type": "text", "text": "Nội dung"}]}

    monkeypatch.setattr(ai_service, "post_anthropic", fake_post)

    ocr_service._read_page_with_vision(b"png", "image/png", "prompt")

    assert captured["model"] == "glm-4.6v"
    assert captured["temperature"] == 0


def test_ocr_vision_model_env_var_is_read(monkeypatch):
    """Tên biến môi trường phải đúng OCR_VISION_MODEL (không phải ANTHROPIC_*)."""
    monkeypatch.setenv("OCR_VISION_MODEL", "deepseek-v4-pro")
    get_settings.cache_clear()
    try:
        assert get_settings().ocr_vision_model == "deepseek-v4-pro"
        assert ocr_service.vision_model() == "deepseek-v4-pro"
    finally:
        get_settings.cache_clear()


def test_all_pages_failing_reports_real_reason(monkeypatch):
    """Trang hỏng cả loạt → message cuối phải kèm nguyên nhân thật."""

    def fake_extract(text: str):
        return ocr_service.empty_structured(), []

    monkeypatch.setattr(ocr_service, "extract_structured", fake_extract)
    monkeypatch.setattr(ai_service, "extract_pdf_pages_markdown", lambda data: [""])
    monkeypatch.setattr(
        ocr_service, "_render_pdf_pages", lambda data, indexes, dpi: {0: (b"p", "image/png")}
    )

    def fake_vision(png, media_type, prompt):
        raise ai_service.AIServiceError("Model 'glm-5.3' cannot read images")

    monkeypatch.setattr(ocr_service, "_read_page_with_vision", fake_vision)

    with pytest.raises(ai_service.AIServiceError) as error:
        ocr_service.ocr_document_bytes(b"%PDF", "application/pdf")

    assert "cannot read images" in str(error.value)
