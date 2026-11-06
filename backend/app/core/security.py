"""Xác minh access token do Supabase Auth cấp.

Token là JWT ký bất đối xứng (RS256/ES256); public key lấy từ endpoint JWKS
của project Supabase. PyJWKClient tự cache key và tự fetch lại khi `kid`
xoay — KHÔNG tự cache vĩnh viễn bằng cách khác. Không verify token tự ký
nữa: toàn bộ đăng nhập (Google + email/password) do Supabase quản lý.
"""

from typing import Any

import jwt
from jwt import PyJWKClient

from app.core.config import Settings, get_settings


class AuthError(Exception):
    """Lỗi xác thực — lớp API map ra HTTP 401 kèm message tiếng Anh."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


# Cache client theo URL project — tránh tạo lại HTTP client mỗi request
_jwk_clients: dict[str, PyJWKClient] = {}


def verify_supabase_token(token: str, *, settings: Settings | None = None) -> dict[str, Any]:
    """Verify chữ ký/issuer/audience/hạn của access token Supabase.

    - Sai chữ ký, sai `iss` (token từ project khác), sai `aud`, hết hạn → AuthError.
    - Không nối được JWKS (Supabase sự cố) → AuthError với message phân biệt.
    - Chỉ nhận chữ ký bất đối xứng từ JWKS → chặn alg confusion (HS256/none).
    """
    s = settings or get_settings()
    client = _jwk_clients.get(s.supabase_url)
    if client is None:
        client = PyJWKClient(s.supabase_jwks_url, cache_keys=True)
        _jwk_clients[s.supabase_url] = client
    try:
        signing_key = client.get_signing_key_from_jwt(token)
        payload: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            issuer=s.supabase_issuer,
            audience="authenticated",
            options={"require": ["exp", "iss", "sub"]},
            # leeway: chấp nhận sai lệch đồng hồ nhỏ giữa máy local và Supabase.
            # Không có leeway, máy chậm dù chỉ 1 giây cũng chối token vừa cấp
            # (iat > giờ máy → ImmatureSignatureError) → login xong bị đá ra.
            leeway=30,
        )
    except jwt.PyJWKClientError as exc:
        raise AuthError("Could not verify the token (Supabase is unreachable)") from exc
    except jwt.PyJWTError as exc:
        raise AuthError("The token is invalid or has expired") from exc
    return payload
