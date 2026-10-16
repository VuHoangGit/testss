"""Tạo (hoặc cập nhật lại) tài khoản demo: hoang@gmail.com / 123456.

Chạy an toàn nhiều lần (idempotent): user đã có → chỉ reset mật khẩu về 123456.

    cd backend
    .\\.venv\\Scripts\\python.exe scripts\\seed_demo_user.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Cho phép chạy trực tiếp `python scripts/seed_demo_user.py` từ thư mục backend
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.passwords import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402

DEMO_EMAIL = "hoang@gmail.com"
DEMO_PASSWORD = "123456"
DEMO_NAME = "Hoàng"


def main() -> None:
    db = SessionLocal()
    try:
        normalized = DEMO_EMAIL.strip().lower()
        user = db.scalar(select(User).where(User.email == normalized))
        if user is None:
            user = User(
                google_sub=None,
                email=normalized,
                name=DEMO_NAME,
                password_hash=hash_password(DEMO_PASSWORD),
            )
            db.add(user)
            action = "create"
        else:
            # Đã có → luôn reset mật khẩu về 123456 để demo chắc chắn đăng nhập được
            user.password_hash = hash_password(DEMO_PASSWORD)
            action = "set-password"
            if not user.name:
                user.name = DEMO_NAME
        db.commit()
        # In ASCII-only: console Windows cp1252 không in được tiếng Việt có dấu
        print(f"[{action}] {normalized} / {DEMO_PASSWORD} (id={user.id})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
