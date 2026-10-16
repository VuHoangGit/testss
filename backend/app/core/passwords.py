"""Hash mật khẩu bằng PBKDF2-HMAC-SHA256 — thư viện chuẩn, không thêm dependency.

Format lưu trong DB: ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>``
(600_000 vòng theo khuyến nghị OWASP 2023 cho SHA-256).
"""

import hashlib
import hmac
import secrets

_ALGO = "sha256"
_ITERATIONS = 600_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Sinh chuỗi hash kèm salt ngẫu nhiên — mỗi lần gọi một salt mới."""
    salt = secrets.token_hex(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(_ALGO, password.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS)
    return f"pbkdf2_{_ALGO}${_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Kiểm tra mật khẩu với chuỗi hash đã lưu; sai format → False (không ném)."""
    try:
        algo_part, iterations_raw, salt_hex, hash_hex = stored.split("$", 3)
        if algo_part != f"pbkdf2_{_ALGO}":
            return False
        digest = hashlib.pbkdf2_hmac(
            _ALGO, password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations_raw)
        )
    except (ValueError, TypeError):
        return False
    # so sánh constant-time để tránh timing attack
    return hmac.compare_digest(digest.hex(), hash_hex)
