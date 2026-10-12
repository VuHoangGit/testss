"""Xác minh id_token do Google cấp: chữ ký (qua JWKS của Google), iss, aud, exp, email_verified.

Backend không tin client — mọi thông tin danh tính đều lấy lại từ token đã verify.
"""

from dataclasses import dataclass

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token as google_id_token

from app.core.config import get_settings
from app.core.security import AuthError

# Google có thể phát hành với 2 dạng issuer (EC-01/03 chặn token của app khác qua check aud/iss)
_VALID_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


@dataclass(slots=True)
class GoogleIdentity:
    """Danh tính đã được Google xác minh."""

    google_sub: str
    email: str
    name: str | None
    avatar_url: str | None


def verify_google_id_token(id_token: str) -> GoogleIdentity:
    """Verify id_token; sai chữ ký/hết hạn/aud sai → AuthError (EC-01/02/03/08)."""
    settings = get_settings()
    try:
        payload = google_id_token.verify_oauth2_token(id_token, GoogleAuthRequest())
    except (ValueError, GoogleAuthError) as exc:
        # google-auth báo token sai định dạng/chữ ký/hết hạn qua ValueError/GoogleAuthError
        raise AuthError("Token Google không hợp lệ hoặc đã hết hạn") from exc

    if payload.get("aud") not in settings.google_client_id_list:
        raise AuthError("Token Google không thuộc ứng dụng này")
    if payload.get("iss") not in _VALID_ISSUERS:
        raise AuthError("Token Google không do Google phát hành")

    email = payload.get("email")
    if not email:
        raise AuthError("Token Google thiếu email")
    if not payload.get("email_verified"):
        raise AuthError("Email Google chưa được xác minh")

    # Giới hạn domain nếu cấu hình (EC-35) — mặc định rỗng = mở cho mọi account
    domains = settings.allowed_email_domain_list
    if domains and not any(email.lower().endswith("@" + d) for d in domains):
        raise AuthError("Email không thuộc domain được phép truy cập")

    return GoogleIdentity(
        google_sub=payload["sub"],
        email=email,
        name=payload.get("name"),
        avatar_url=payload.get("picture"),
    )
