"""Test bảo mật: xác thực, phân quyền, upload, quota, rate limit, header, CORS.

Các case ở đây bám đúng lỗi đã rà: upload không giới hạn bộ nhớ/đuôi file, thiếu
rate limit ở endpoint tốn tiền, MIME do client khai, CORS dev bật vô điều kiện,
webhook không đối chiếu tài khoản nhận.
"""

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.ratelimit import reset_rate_limits
from app.main import create_app
from app.models.document import Document


@contextmanager
def _env(**values: str) -> Iterator[None]:
    """Tạm đổi biến môi trường (ưu tiên hơn file .env) rồi khôi phục."""
    previous = {key: os.environ.get(key) for key in values}
    try:
        os.environ.update(values)
        get_settings.cache_clear()
        yield
    finally:
        for key, old in previous.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        get_settings.cache_clear()


def _headers(make_token, sub: str, email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub=sub, email=email)}"}


def _upload(client: TestClient, headers: dict[str, str], name: str, data: bytes, mime: str):
    return client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": (name, data, mime)},
    )


class TestAuthentication:
    def test_documents_requires_token(self, client: TestClient) -> None:
        assert client.get("/api/v1/documents").status_code == 401

    def test_ai_requires_token(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/ai/translate", json={"text": "hello", "target_language": "Vietnamese"}
        )
        assert response.status_code == 401

    def test_document_of_another_user_is_invisible(self, client, make_token) -> None:
        """IDOR: user B không đọc được tài liệu của user A (trả 404, không 403)."""
        owner = _headers(make_token, "sub-a", "a@gmail.com")
        other = _headers(make_token, "sub-b", "b@gmail.com")
        doc = _upload(client, owner, "rieng.txt", b"noi dung rieng", "text/plain").json()

        download = client.get(f"/api/v1/documents/{doc['id']}/download", headers=other)
        delete = client.delete(f"/api/v1/documents/{doc['id']}", headers=other)
        assert (download.status_code, delete.status_code) == (404, 404)


class TestUploadHardening:
    def test_rejects_unknown_extension(self, client, make_token) -> None:
        headers = _headers(make_token, "sub-ext", "ext@gmail.com")
        response = _upload(client, headers, "virus.exe", b"MZ", "application/octet-stream")
        assert response.status_code == 415
        assert "pdf" in response.json()["detail"]

    def test_uses_server_side_mime_not_client_claim(self, client, make_token) -> None:
        """Client khai text/html cho file .png → server vẫn lưu image/png."""
        headers = _headers(make_token, "sub-mime", "mime@gmail.com")
        response = _upload(client, headers, "anh.png", b"\x89PNG", "text/html")
        assert response.status_code == 201
        assert response.json()["mime_type"] == "image/png"

    def test_rejects_file_over_size_limit(self, client, make_token) -> None:
        headers = _headers(make_token, "sub-big", "big@gmail.com")
        with _env(MAX_UPLOAD_MB="1"):
            response = _upload(client, headers, "to.txt", b"x" * (1024 * 1024 + 1), "text/plain")
        assert response.status_code == 413

    def test_enforces_storage_quota(self, client, make_token) -> None:
        headers = _headers(make_token, "sub-quota", "quota@gmail.com")
        with _env(USER_STORAGE_QUOTA_MB="1"):
            first = _upload(client, headers, "a.txt", b"x" * 600_000, "text/plain")
            second = _upload(client, headers, "b.txt", b"x" * 600_000, "text/plain")
        assert first.status_code == 201
        assert second.status_code == 413
        assert "quota" in second.json()["detail"].lower()

    def test_reports_storage_usage(self, client, make_token) -> None:
        headers = _headers(make_token, "sub-usage", "usage@gmail.com")
        _upload(client, headers, "a.txt", b"12345", "text/plain")
        usage = client.get("/api/v1/documents/usage", headers=headers).json()
        assert usage["used_bytes"] == 5
        assert usage["quota_bytes"] is None or usage["quota_bytes"] > 0

    def test_download_of_unsafe_mime_is_octet_stream(
        self, client, make_token, db_session_factory
    ) -> None:
        """Dữ liệu cũ có mime do client khai (text/html) → tải về dạng nhị phân."""
        headers = _headers(make_token, "sub-dl", "dl@gmail.com")
        doc = _upload(client, headers, "note.txt", b"xin chao", "text/plain").json()
        with db_session_factory() as db:
            row = db.get(Document, uuid.UUID(doc["id"]))
            row.mime_type = "text/html"
            db.commit()

        response = client.get(f"/api/v1/documents/{doc['id']}/download", headers=headers)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/octet-stream"
        assert response.headers["x-content-type-options"] == "nosniff"


class TestRateLimit:
    def test_ai_endpoint_returns_429_after_limit(self, client, make_token, monkeypatch) -> None:
        reset_rate_limits()
        monkeypatch.setattr(
            "app.api.v1.ai.ai_service.translate_selection",
            lambda text, target, source_language=None: "ok",
        )
        headers = _headers(make_token, "sub-rate", "rate@gmail.com")
        body = {"text": "hello", "target_language": "Vietnamese"}
        try:
            with _env(RATE_LIMIT_ENABLED="true", RATE_LIMIT_AI_PER_MINUTE="2"):
                first = client.post("/api/v1/ai/translate", headers=headers, json=body)
                second = client.post("/api/v1/ai/translate", headers=headers, json=body)
                third = client.post("/api/v1/ai/translate", headers=headers, json=body)
            assert (first.status_code, second.status_code) == (200, 200)
            assert third.status_code == 429
            assert int(third.headers["retry-after"]) >= 1
        finally:
            reset_rate_limits()

    def test_upload_endpoint_returns_429_after_limit(self, client, make_token) -> None:
        reset_rate_limits()
        headers = _headers(make_token, "sub-rate-up", "rate2@gmail.com")
        try:
            with _env(RATE_LIMIT_ENABLED="true", RATE_LIMIT_UPLOAD_PER_MINUTE="1"):
                first = _upload(client, headers, "a.txt", b"x", "text/plain")
                second = _upload(client, headers, "b.txt", b"x", "text/plain")
            assert first.status_code == 201
            assert second.status_code == 429
        finally:
            reset_rate_limits()

    def test_limit_is_per_user(self, client, make_token, monkeypatch) -> None:
        """User này hết hạn mức không ảnh hưởng user khác."""
        reset_rate_limits()
        monkeypatch.setattr(
            "app.api.v1.ai.ai_service.translate_selection",
            lambda text, target, source_language=None: "ok",
        )
        body = {"text": "hello", "target_language": "Vietnamese"}
        try:
            with _env(RATE_LIMIT_ENABLED="true", RATE_LIMIT_AI_PER_MINUTE="1"):
                first_user = _headers(make_token, "sub-r1", "r1@gmail.com")
                second_user = _headers(make_token, "sub-r2", "r2@gmail.com")
                client.post("/api/v1/ai/translate", headers=first_user, json=body)
                blocked = client.post("/api/v1/ai/translate", headers=first_user, json=body)
                allowed = client.post("/api/v1/ai/translate", headers=second_user, json=body)
            assert blocked.status_code == 429
            assert allowed.status_code == 200
        finally:
            reset_rate_limits()


class TestResponseHeaders:
    def test_security_headers_present(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"


class TestCors:
    def test_public_origin_rejected_in_production(self) -> None:
        with _env(ENVIRONMENT="production", CORS_ORIGINS=""):
            with TestClient(create_app()) as prod_client:
                response = prod_client.get(
                    "/openapi.json", headers={"Origin": "https://evil.example.com"}
                )
        assert "access-control-allow-origin" not in response.headers

    def test_lan_origin_rejected_in_production(self) -> None:
        """Regex LAN chỉ bật ở dev — production phải khai báo CORS_ORIGINS."""
        with _env(ENVIRONMENT="production", CORS_ORIGINS=""):
            with TestClient(create_app()) as prod_client:
                response = prod_client.get(
                    "/openapi.json", headers={"Origin": "http://192.168.1.20:53123"}
                )
        assert "access-control-allow-origin" not in response.headers

    def test_configured_origin_allowed_in_production(self) -> None:
        with _env(ENVIRONMENT="production", CORS_ORIGINS="https://app.example.com"):
            with TestClient(create_app()) as prod_client:
                response = prod_client.get(
                    "/openapi.json", headers={"Origin": "https://app.example.com"}
                )
        assert response.headers["access-control-allow-origin"] == "https://app.example.com"


class TestSepayWebhookAccount:
    def test_payment_to_other_account_is_ignored(self, client, make_token) -> None:
        headers = _headers(make_token, "sub-pay", "pay@gmail.com")
        with _env(SEPAY_WEBHOOK_SECRET="test-secret", SEPAY_BANK_ACCOUNT="0123456789"):
            order = client.post(
                "/api/v1/payments/orders", headers=headers, json={"code": "P50"}
            ).json()
            response = client.post(
                "/api/v1/payments/sepay/webhook",
                json={
                    "content": order["transfer_content"],
                    "transferAmount": order["amount_vnd"],
                    "transferType": "in",
                    "transactionNumber": "T-OTHER-1",
                    "accountNumber": "9999999999",
                },
                headers={"X-Webhook-Secret": "test-secret"},
            )
            credits = client.get("/api/v1/payments/credits", headers=headers).json()

        assert response.status_code == 202
        assert "accountNumber" in response.json()["result"]
        assert credits["purchased"] == 0
