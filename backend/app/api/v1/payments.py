"""API thanh toán: gói credit, số dư, đơn nạp + webhook SePay."""

import logging
import secrets
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.schemas.payment import (
    CreateOrderRequest,
    CreditBalanceOut,
    OrderOut,
    PackageOut,
)
from app.services import credit_service, payment_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("/pricing", response_model=list[PackageOut])
def list_pricing(db: DbSession, current: CurrentUser) -> list[PackageOut]:
    """Danh sách gói credit đang bán."""
    return payment_service.list_packages(db)


@router.get("/credits", response_model=CreditBalanceOut)
def get_credits(db: DbSession, current: CurrentUser) -> CreditBalanceOut:
    """Số dư credit của user (reset 300 free đầu tháng, lazy)."""
    settings = get_settings()
    credit_service.ensure_monthly_refresh(db, current)
    return CreditBalanceOut(
        free=current.credit_free,
        purchased=current.credit_purchased,
        total=current.credit_free + current.credit_purchased,
        monthly_free=settings.credit_monthly_free,
        ai_cost=settings.credit_cost_ai,
    )


@router.post("/orders", response_model=OrderOut, status_code=201)
def create_order(
    body: CreateOrderRequest, db: DbSession, current: CurrentUser
) -> OrderOut:
    """Tạo đơn nạp: trả mã đơn + nội dung chuyển khoản + QR để thanh toán."""
    try:
        order = payment_service.create_order(db, current, body.code.strip())
    except payment_service.PackageNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return OrderOut.from_order(order)


@router.get("/orders", response_model=list[OrderOut])
def list_orders(db: DbSession, current: CurrentUser) -> list[OrderOut]:
    """Lịch sử thanh toán của user (mới nhất trước)."""
    return [
        OrderOut.from_order(o) for o in payment_service.list_orders(db, current)
    ]


@router.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: str, db: DbSession, current: CurrentUser) -> OrderOut:
    """Trạng thái 1 đơn — UI poll endpoint này khi chờ chuyển khoản."""
    try:
        order_uuid = uuid.UUID(order_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn") from exc
    order = payment_service.get_order(db, order_uuid, current)
    if order is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn")
    return OrderOut.from_order(order)


@router.post("/sepay/webhook", status_code=202)
def receive_sepay_webhook(
    payload: dict[str, Any],
    db: DbSession,
    authorization: str | None = Header(default=None),
    x_webhook_secret: str | None = Header(default=None),
) -> dict[str, str]:
    """Nhận giao dịch tiền vào từ SePay → đối chiếu đơn → cộng credit.

    SePay gọi endpoint này không kèm access token của người dùng. Secret phải
    được cấu hình ở backend và nhập vào phần bảo mật của webhook trên SePay
    (SePay gửi kèm header `X-Webhook-Secret`).

    Luôn trả 2xx khi secret hợp lệ để SePay không retry vô hạn; giao dịch
    không khớp đơn nào chỉ được log, không ảnh hưởng dữ liệu.
    """
    configured_secret = get_settings().sepay_webhook_secret.strip()
    if not configured_secret:
        raise HTTPException(
            status_code=503,
            detail="SEPAY_WEBHOOK_SECRET chưa được cấu hình trên backend",
        )

    bearer_secret = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer_secret = authorization[7:].strip()
    received_secret = x_webhook_secret or bearer_secret
    if not received_secret or not secrets.compare_digest(received_secret, configured_secret):
        raise HTTPException(status_code=401, detail="Webhook secret không hợp lệ")

    if not payload:
        raise HTTPException(status_code=400, detail="Webhook payload không được rỗng")

    result = payment_service.process_sepay_webhook(db, payload)
    logger.info("SePay webhook: %s", result)
    return {"status": "received", "result": result}
