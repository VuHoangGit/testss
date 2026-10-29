"""Tạo bảng `ai_conversations` + `ai_messages` trong DB đang chạy (chạy 1 lần).

DB đã có dữ liệu thật (SQLite local) nên KHÔNG drop/recreate: chỉ CREATE TABLE
IF NOT EXISTS kèm index (tạo qua metadata của model để khớp chính xác schema).
Idempotent — chạy lại không lỗi, không đụng dữ liệu cũ.

Chạy:  python scripts/migrate_add_ai_chat.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect  # noqa: E402

from app.db.session import engine  # noqa: E402
from app.models.conversation import AiConversation  # noqa: E402
from app.models.message import AiMessage  # noqa: E402


def main() -> int:
    inspector = inspect(engine)
    has_conversations = inspector.has_table(AiConversation.__tablename__)
    has_messages = inspector.has_table(AiMessage.__tablename__)
    if has_conversations and has_messages:
        print("Bang ai_conversations/ai_messages da ton tai — khong lam gi them.")
        return 0

    # checkfirst để không lỗi khi chỉ 1 trong 2 bảng đã có
    AiConversation.__table__.create(engine, checkfirst=True)
    AiMessage.__table__.create(engine, checkfirst=True)
    print("Da tao bang ai_conversations + ai_messages (kem FK, index).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
