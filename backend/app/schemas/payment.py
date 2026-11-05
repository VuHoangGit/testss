"""Schema API thanh toán: gói credit, số dư, đơn nạp."""

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


class CreditBalanceOut(BaseModel):
    free: int
    purchased: int
    total: int
    monthly_free: int
    ai_cost: int


class CreateOrderRequest(BaseModel):
    """Mã gói lấy từ GET /payments/pricing (vd "P1000")."""

    code: str


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_code: str
    status: str  # pending | paid | cancelled
    amount_vnd: int
    credits: int
    transfer_content: str
    qr_url: str | None
    created_at: datetime
    paid_at: datetime | None
    # Thông tin tài khoản nhận để UI hiện cạnh QR (rỗng nếu chưa cấu hình)
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
            # QR suy ra được từ (số tiền, nội dung, cấu hình) nên tính lúc đọc
            # thay vì dùng cột đã lưu: đổi cấu hình TK nhận hoặc sửa công thức
            # URL là mọi đơn cũ (kể cả đơn đang chờ) hiện đúng ngay, không cần
            # tạo lại đơn.
            "qr_url": build_qr_url(order.amount_vnd, order.transfer_content),
        }
        for field in (
            "id",
            "order_code",
            "status",
            "amount_vnd",
            "credits",
            "transfer_content",
            "created_at",
            "paid_at",
        ):
            data[field] = getattr(order, field)
        return cls(**data)
