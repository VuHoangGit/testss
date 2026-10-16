"""Đăng nhập bằng mật khẩu: google_sub cho phép NULL (tài khoản local), thêm password_hash

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-12

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # batch_alter_table: SQLite không ALTER COLUMN trực tiếp — batch mode render
    # create/drop bảng tạm; trên PostgreSQL vẫn là ALTER thường.
    with op.batch_alter_table("users") as batch:
        batch.alter_column("google_sub", existing_type=sa.String(length=255), nullable=True)
        batch.add_column(sa.Column("password_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("password_hash")
        batch.alter_column("google_sub", existing_type=sa.String(length=255), nullable=False)
