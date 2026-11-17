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


def test_connection_error_reports_reachable_hint(monkeypatch):
    """Lỗi kết nối (DNS/mạng đứt) → câu lỗi phải nêu địa chỉ gateway."""
    def fake_post(url, headers=None, json=None, timeout=None):
        raise requests.ConnectionError(
            "HTTPSConnectionPool(host='dev-gw.vtvlive.vn', port=443): "
            "Max retries exceeded"
        )

    monkeypatch.setattr(ai_service.requests, "post", fake_post)

    with pytest.raises(ai_service.AIServiceError) as error:
        ai_service.request_anthropic([{"type": "text", "text": "xin chào"}])

    assert "Cannot reach the AI service" in str(error.value)
    assert "dev-gw.vtvlive.vn" in str(error.value)


def test_read_timeout_gets_specific_message(monkeypatch):
    """Gateway trả lời chậm hơn timeout → câu 'took too long', không phải 'connect'."""
    def fake_post(url, headers=None, json=None, timeout=None):
        raise requests.ReadTimeout("Read timed out. (read timeout=90)")

    monkeypatch.setattr(ai_service.requests, "post", fake_post)

    with pytest.raises(ai_service.AIServiceError) as error:
        ai_service.request_anthropic([{"type": "text", "text": "xin chào"}])

    assert "took too long" in str(error.value)


def test_gateway_5xx_gets_specific_message(monkeypatch):
    """Gateway lỗi nội bộ (5xx) → câu riêng, không lẫn với mất kết nối."""
    body = {"error": {"message": "upstream error"}}

    def fake_post(url, headers=None, json=None, timeout=None):
        raise requests.HTTPError(response=_FakeResponse(502, body))

    monkeypatch.setattr(ai_service.requests, "post", fake_post)

    with pytest.raises(ai_service.AIServiceError) as error:
        ai_service.request_anthropic([{"type": "text", "text": "xin chào"}])

    assert "HTTP 502" in str(error.value)


def test_rate_limit_429_gets_specific_message(monkeypatch):
    """429 rate-limit → câu riêng hướng dẫn thử lại."""
    body = {"error": {"message": "rate limit exceeded"}}

    def fake_post(url, headers=None, json=None, timeout=None):
        raise requests.HTTPError(response=_FakeResponse(429, body))

    monkeypatch.setattr(ai_service.requests, "post", fake_post)

    with pytest.raises(ai_service.AIServiceError) as error:
        ai_service.request_anthropic([{"type": "text", "text": "xin chào"}])

    assert "rate limiting" in str(error.value)


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


def test_google_adapter_translates_payload_and_response():
    """Adapter Gemini: payload Anthropic dịch sang generateContent và ngược lại."""
    payload = {
        "model": "gemini-3.8-pro",
        "max_tokens": 1024,
        "temperature": 0,
        "system": "Bạn là trợ lý.",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Đọc ảnh này"},
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/png", "data": "QUJD",
                }},
            ],
        }],
        "tools": [{
            "name": "open_folder",
            "description": "Mở thư mục",
            "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}},
        }],
    }
    google_body = ai_service._to_google_payload(payload)

    contents = google_body["contents"]
    assert len(contents) == 1
    assert contents[0]["role"] == "user"
    assert {"text": "Đọc ảnh này"} in contents[0]["parts"]
    assert {
        "inlineData": {"mimeType": "image/png", "data": "QUJD"}
    } in contents[0]["parts"]
    assert google_body["systemInstruction"] == {"parts": [{"text": "Bạn là trợ lý."}]}
    config = google_body["generationConfig"]
    assert config["maxOutputTokens"] == 1024
    assert config["temperature"] == 0
    assert config["thinkingConfig"] == {"thinkingBudget": 0}
    assert google_body["tools"][0]["functionDeclarations"][0]["name"] == "open_folder"
    assert (
        google_body["tools"][0]["functionDeclarations"][0]["parameters"]["properties"]
        == {"name": {"type": "string"}}
    )

    google_response = {
        "candidates": [{
            "content": {"parts": [
                {"text": "Kết quả OCR"},
                {"functionCall": {"name": "open_folder", "args": {"name": "Hóa đơn"}}},
            ]}
        }]
    }
    blocks = ai_service._to_anthropic_response(google_response)["content"]
    assert blocks[0] == {"type": "text", "text": "Kết quả OCR"}
    assert blocks[1]["type"] == "tool_use"
    assert blocks[1]["name"] == "open_folder"
    assert blocks[1]["input"] == {"name": "Hóa đơn"}


def test_google_adapter_maps_model_names():
    """haiku/sonnet/opus → flash (key AQ.* chỉ được cấp flash), gemini-* giữ nguyên."""
    assert ai_service._google_model_name("claude-haiku-4-5") == "gemini-3.8-flash"
    assert ai_service._google_model_name("claude-sonnet-4-5") == "gemini-3.8-flash"
    assert ai_service._google_model_name("claude-opus-4-5") == "gemini-3.8-flash"
    assert ai_service._google_model_name("gemini-2.0-flash") == "gemini-2.0-flash"


def test_google_adapter_error_message_from_404(monkeypatch):
    """Google trả 404 model không tồn tại → lỗi phải nêu đúng model, không 'connect'."""
    body = {"error": {"code": 404, "message": "model gemini-99 not found"}}

    class _Resp:
        status_code = 404
        def json(self):
            return body
        def raise_for_status(self):
            raise requests.HTTPError(response=self)

    def fake_post(url, headers=None, json=None, timeout=None):
        return _Resp()

    monkeypatch.setattr(ai_service.requests, "post", fake_post)

    class _Settings:
        anthropic_auth_token = "AQ.test"
        anthropic_base_url = "https://generativelanguage.googleapis.com"
        anthropic_model = "gemini-99"
        anthropic_timeout_seconds = 30

    monkeypatch.setattr(ai_service, "get_settings", lambda: _Settings())

    with pytest.raises(ai_service.AIServiceError) as error:
        ai_service.post_anthropic({"model": "gemini-99"})

    assert "gemini-99" in str(error.value)
    assert "Could not connect" not in str(error.value)
