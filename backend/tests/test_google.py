"""Test app.core.google: verify id_token với verify_oauth2_token mock (không gọi Google thật)."""

from unittest.mock import patch

import pytest
from google.auth.exceptions import GoogleAuthError

from app.core.config import Settings
from app.core.google import GoogleIdentity, verify_google_id_token
from app.core.security import AuthError

WEB_CLIENT_ID = "test-web-client-id.apps.googleusercontent.com"

_BASE_PAYLOAD = {
    "sub": "g-123",
    "email": "a@gmail.com",
    "email_verified": True,
    "name": "Nguyễn Văn A",
    "picture": "https://lh3.googleusercontent.com/a.jpg",
    "aud": WEB_CLIENT_ID,
    "iss": "https://accounts.google.com",
    "exp": 9999999999,
}


def _patch_verify(payload):
    return patch(
        "app.core.google.google_id_token.verify_oauth2_token", return_value=payload
    )


def test_valid_token_returns_identity():
    with _patch_verify(dict(_BASE_PAYLOAD)):
        identity = verify_google_id_token("token")
    assert isinstance(identity, GoogleIdentity)
    assert identity.google_sub == "g-123"
    assert identity.email == "a@gmail.com"
    assert identity.name == "Nguyễn Văn A"
    assert identity.avatar_url == "https://lh3.googleusercontent.com/a.jpg"


def test_wrong_audience_rejected():  # EC-01/EC-10
    payload = dict(_BASE_PAYLOAD, aud="client-cua-app-khac")
    with _patch_verify(payload), pytest.raises(AuthError, match="không thuộc ứng dụng"):
        verify_google_id_token("token")


def test_bad_issuer_rejected():  # EC-03
    payload = dict(_BASE_PAYLOAD, iss="https://evil.example.com")
    with _patch_verify(payload), pytest.raises(AuthError, match="không do Google"):
        verify_google_id_token("token")


def test_email_not_verified_rejected():  # EC-08
    payload = dict(_BASE_PAYLOAD, email_verified=False)
    with _patch_verify(payload), pytest.raises(AuthError, match="chưa được xác minh"):
        verify_google_id_token("token")


def test_missing_email_rejected():
    payload = {k: v for k, v in _BASE_PAYLOAD.items() if k != "email"}
    with _patch_verify(payload), pytest.raises(AuthError, match="thiếu email"):
        verify_google_id_token("token")


@pytest.mark.parametrize(
    "side_effect",
    [ValueError("Token expired"), GoogleAuthError("signature fail")],
)
def test_google_lib_errors_map_to_auth_error(side_effect):
    with (
        patch(
            "app.core.google.google_id_token.verify_oauth2_token",
            side_effect=side_effect,
        ),
        pytest.raises(AuthError),
    ):
        verify_google_id_token("token")


def test_allowed_email_domains_whitelist(monkeypatch):  # EC-35
    custom = Settings(
        jwt_secret="x" * 32, google_client_ids=WEB_CLIENT_ID, allowed_email_domains="congty.vn"
    )
    monkeypatch.setattr("app.core.google.get_settings", lambda: custom)

    with _patch_verify(dict(_BASE_PAYLOAD, email="user@CONGTY.VN")):
        verify_google_id_token("token")  # cùng domain (không phân biệt hoa/thường) → pass

    with (
        _patch_verify(dict(_BASE_PAYLOAD, email="user@gmail.com")),
        pytest.raises(AuthError, match="không thuộc domain"),
    ):
        verify_google_id_token("token")


def test_open_registration_when_no_domain_configured():  # EC-35 mặc định
    with _patch_verify(dict(_BASE_PAYLOAD, email="bat-ky@gmail.com")):
        verify_google_id_token("token")  # rỗng = mở cho mọi account
