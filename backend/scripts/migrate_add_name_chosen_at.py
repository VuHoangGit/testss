"""Thêm cột `name_chosen_at` vào bảng `users` của DB đang chạy (chạy 1 lần).

Cột đánh dấu người dùng đã TỰ đặt tên hiển thị hay chưa: NULL = chưa → app
hiện màn đặt tên ngay sau khi đăng nhập. DB đang có dữ liệu thật nên KHÔNG
drop/recreate: chỉ ALTER TABLE thêm cột nullable. Idempotent — chạy lại không
lỗi. User cũ sẽ có NULL (được hỏi tên một lần), đúng ý định.

Chạy:  python scripts/migrate_add_name_chosen_at.py
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
        print("Với Postgres hãy chạy ALTER TABLE users ADD COLUMN name_chosen_at TIMESTAMP;")
        return 0
    db_path = url.removeprefix("sqlite:///")
    if not Path(db_path).exists():
        print(f"Không tìm thấy DB tại {db_path} — không có gì để migrate.")
        return 1

    conn = sqlite3.connect(db_path)
    try:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(users)")]
        if "name_chosen_at" in columns:
            print("Cot name_chosen_at da ton tai — khong lam gi them.")
            return 0
        conn.execute("ALTER TABLE users ADD COLUMN name_chosen_at DATETIME")
        conn.commit()
        print("Da them cot name_chosen_at cho bang users.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
