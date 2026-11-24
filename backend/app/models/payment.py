"""Payment tables: pricing packages + payment orders.

Packages are configuration data (seeded idempotently by `code`). Each order
gets a unique `DVXXXXXX` code embedded in the bank transfer content — the
SePay webhook matches code + amount to activate the purchase automatically.
`sepay_transaction_id` is UNIQUE to prevent processing the same bank
transaction twice.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime


class PricingPackage(Base):
    """Monthly subscription plans (FREE/PLUS/PRO/MAX).

    `credits` is the monthly quota the plan grants (not a one-time top-up);
    `unlimited=True` (MAX) shows as "Unlimited" in the UI while the backend
    still enforces fair-use limits from settings.
    """

    __tablename__ = "pricing_packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stable code used by clients ("PLUS") — seeded by code, price edits keep id
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    price_vnd: Mapped[int] = mapped_column(Integer, nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    # Marketing label ("Most popular") rendered as a chip on the pricing screen
    badge: Mapped[str | None] = mapped_column(String(40), default=None)
    active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # True for the Max plan — UI renders "Unlimited" instead of a credit count.
    unlimited: Mapped[bool] = mapped_column(default=False)


class PaymentOrder(Base):
    """A purchase order: pending → paid (once the webhook matches it)."""

    __tablename__ = "payment_orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    package_id: Mapped[int] = mapped_column(
        ForeignKey("pricing_packages.id"), nullable=False
    )
    # "DV" + 6 chars (ambiguous letters/digits dropped) — copied into the
    # bank transfer content by the user
    order_code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    amount_vnd: Mapped[int] = mapped_column(Integer, nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    # pending | paid | cancelled
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    # Plan the order bought (PLUS/PRO/MAX) — snapshotted at creation time.
    plan_code: Mapped[str] = mapped_column(String(16), default="")
    transfer_content: Mapped[str] = mapped_column(String(64))
    # QR image URL saved at order creation — reference only. The API does NOT
    # read this column; it recomputes the QR from (amount_vnd,
    # transfer_content, SePay config) on every read, so changing the receiving
    # account config immediately fixes old orders too.
    qr_url: Mapped[str | None] = mapped_column(Text, default=None)
    # Bank transaction id (SePay transactionNumber/code) — UNIQUE, prevents
    # crediting the same transaction twice
    sepay_transaction_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), nullable=False
    )
    paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    package: Mapped[PricingPackage] = relationship()
