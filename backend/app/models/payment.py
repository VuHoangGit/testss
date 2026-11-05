"""Bảng thanh toán: gói credit (`pricing_packages`) + đơn nạp (`payment_orders`).

Gói là dữ liệu cấu hình (seed idempotent theo `code`). Mỗi đơn nạp sinh mã
`DVXXXXXX` duy nhất nhúng vào nội dung chuyển khoản — webhook SePay đối chiếu
mã + số tiền để tự động cộng credit. `sepay_transaction_id` UNIQUE chống xử
lý trùng 1 giao dịch ngân hàng.
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime


class PricingPackage(Base):
    """Gói nạp credit (100k→1.000, 200k→2.500, 500k→10.000)."""

    __tablename__ = "pricing_packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Mã ổn định dùng từ client ("P1000") — seed theo code, đổi giá vẫn giữ id
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    price_vnd: Mapped[int] = mapped_column(Integer, nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class PaymentOrder(Base):
    """Đơn nạp credit: pending → paid (webhook đối chiếu xong)."""

    __tablename__ = "payment_orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    package_id: Mapped[int] = mapped_column(
        ForeignKey("pricing_packages.id"), nullable=False
    )
    # "DV" + 6 ký tự (bỏ chữ/số dễ nhầm) — người dùng copy vào nội dung CK
    order_code: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    amount_vnd: Mapped[int] = mapped_column(Integer, nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    # pending | paid | cancelled
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    transfer_content: Mapped[str] = mapped_column(String(64))
    # URL ảnh QR ghi lại lúc tạo đơn — chỉ để tra cứu. API KHÔNG dùng cột này
    # mà tính lại từ (amount_vnd, transfer_content, cấu hình SePay) mỗi lần đọc,
    # nhờ vậy đổi cấu hình TK nhận là đơn cũ hiện đúng ngay.
    qr_url: Mapped[str | None] = mapped_column(Text, default=None)
    # Mã giao dịch ngân hàng (transactionNumber/code của SePay) — UNIQUE
    # chống cộng credit 2 lần cho cùng 1 giao dịch
    sepay_transaction_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), nullable=False
    )
    paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    package: Mapped[PricingPackage] = relationship()
