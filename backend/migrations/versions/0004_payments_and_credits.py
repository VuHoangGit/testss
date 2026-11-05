"""Add credit balances, pricing packages, and payment orders.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "credit_free" not in user_columns:
        with op.batch_alter_table("users") as batch:
            batch.add_column(
                sa.Column("credit_free", sa.Integer(), nullable=False, server_default="300")
            )
            batch.add_column(
                sa.Column("credit_purchased", sa.Integer(), nullable=False, server_default="0")
            )
            batch.add_column(
                sa.Column("credit_period", sa.String(length=7), nullable=False, server_default="")
            )

    if not inspector.has_table("pricing_packages"):
        op.create_table(
            "pricing_packages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(length=16), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("price_vnd", sa.Integer(), nullable=False),
            sa.Column("credits", sa.Integer(), nullable=False),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.UniqueConstraint("code", name="uq_pricing_packages_code"),
        )
        op.create_index("ix_pricing_packages_code", "pricing_packages", ["code"], unique=True)

    if not inspector.has_table("payment_orders"):
        op.create_table(
            "payment_orders",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column(
                "user_id",
                sa.Uuid(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "package_id",
                sa.Integer(),
                sa.ForeignKey("pricing_packages.id"),
                nullable=False,
            ),
            sa.Column("order_code", sa.String(length=8), nullable=False),
            sa.Column("amount_vnd", sa.Integer(), nullable=False),
            sa.Column("credits", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
            sa.Column("transfer_content", sa.String(length=64), nullable=False),
            sa.Column("qr_url", sa.Text(), nullable=True),
            sa.Column("sepay_transaction_id", sa.String(length=64), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("order_code", name="uq_payment_orders_order_code"),
            sa.UniqueConstraint(
                "sepay_transaction_id", name="uq_payment_orders_sepay_transaction_id"
            ),
        )
        op.create_index("ix_payment_orders_user_id", "payment_orders", ["user_id"])
        op.create_index(
            "ix_payment_orders_order_code", "payment_orders", ["order_code"], unique=True
        )
        op.create_index("ix_payment_orders_status", "payment_orders", ["status"])


def downgrade() -> None:
    op.drop_table("payment_orders")
    op.drop_index("ix_pricing_packages_code", table_name="pricing_packages")
    op.drop_table("pricing_packages")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("credit_period")
        batch.drop_column("credit_purchased")
        batch.drop_column("credit_free")
