"""Payments schemas: subscription plans, credit balance, orders."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.config import get_settings
from app.models.payment import PaymentOrder
from app.services.payment_service import build_qr_url


class PackageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    price_vnd: int
    credits: int
    badge: str | None = None
    unlimited: bool = False


class CreditBalanceOut(BaseModel):
    free: int
    purchased: int
    total: int
    monthly_free: int
    ai_cost: int
    plan_code: str = "FREE"
    unlimited: bool = False
    plan_expires_at: datetime | None = None


class CreateOrderRequest(BaseModel):
    """Plan code from GET /payments/pricing (e.g. "PLUS")."""

    code: str


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_code: str
    status: str  # pending | paid | cancelled
    amount_vnd: int
    credits: int
    plan_code: str = ""
    transfer_content: str
    qr_url: str | None
    created_at: datetime
    paid_at: datetime | None
    # Receiving account info shown next to the QR (empty when unconfigured)
    bank_bin: str = ""
    bank_account: str = ""
    account_name: str = ""

    @classmethod
    def from_order(cls, order: PaymentOrder) -> "OrderOut":
        settings = get_settings()
        data = {
            "bank_bin": settings.sepay_bank_bin.strip(),
            "bank_account": settings.sepay_bank_account.strip(),
            "account_name": settings.sepay_account_name.strip(),
            # The QR is derivable from (amount, content, config), so compute it
            # on read instead of using the stored column: changing the
            # receiving account or the URL formula instantly fixes every old
            # order (including pending ones) without recreating them.
            "qr_url": build_qr_url(order.amount_vnd, order.transfer_content),
        }
        for field in (
            "id",
            "order_code",
            "status",
            "amount_vnd",
            "credits",
            "plan_code",
            "transfer_content",
            "created_at",
            "paid_at",
        ):
            data[field] = getattr(order, field)
        return cls(**data)
