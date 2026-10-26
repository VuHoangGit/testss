"""Thêm cột `supabase_id` vào bảng `users` của DB đang chạy (chạy 1 lần).

DB đã có dữ liệu thật (SQLite local) nên KHÔNG drop/recreate: chỉ ALTER TABLE
thêm cột nullable + unique index (nhiều NULL hợp lệ). Idempotent — chạy lại
không lỗi. Cột cũ google_sub/password_hash giữ nguyên trong DB (lịch sử),
không còn dùng từ khi chuyển auth sang Supabase.

Chạy:  python scripts/migrate_add_supabase_id.py
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402


def main() -> int:
    url = get_settings().database_url
    if not url.startswith("sqlite"):
        print(f"Bỏ qua: DATABASE_URL không phải SQLite ({url.split('://')[0]}).")
        print("Với Postgres hãy chạy CREATE TABLE mới qua create_all hoặc Alembic.")
        return 0
    db_path = url.removeprefix("sqlite:///")
    if not Path(db_path).exists():
        print(f"Không tìm thấy DB tại {db_path} — không có gì để migrate.")
        return 1

    conn = sqlite3.connect(db_path)
    try:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(users)")]
        if "supabase_id" in columns:
            print("Cot supabase_id da ton tai — khong lam gi them.")
            return 0
        conn.execute("ALTER TABLE users ADD COLUMN supabase_id VARCHAR(64)")
        conn.execute("CREATE UNIQUE INDEX ix_users_supabase_id ON users (supabase_id)")
        conn.commit()
        print("Da them cot supabase_id + unique index cho bang users.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
