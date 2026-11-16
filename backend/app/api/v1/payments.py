"""API thanh toán: gói credit, số dư, đơn nạp + webhook SePay."""

import hashlib
import logging
import secrets
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.deps import CurrentUser, DbSession, order_rate_limit
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


def _fingerprint(value: str) -> str:
    """8 ký tự đầu SHA-256 — so khớp secret trong log mà không lộ giá trị thật."""
    return hashlib.sha256(value.encode()).hexdigest()[:8]


# SePay gửi `Authorization: Apikey <key>` khi webhook chọn "API Key" — KHÔNG phải
# "Bearer". Nhận cả hai (và `Token`) để cấu hình kiểu nào cũng chạy.
_AUTH_SCHEMES = ("bearer", "apikey", "api-key", "token")


def _parse_authorization(header: str | None) -> tuple[str, str | None]:
    """Tách `Authorization` → (tên scheme để log, secret) — secret None nếu lạ."""
    if not header:
        return "KHÔNG CÓ HEADER NÀO", None
    scheme, _, value = header.partition(" ")
    scheme = scheme.strip().lower()
    value = value.strip()
    if scheme not in _AUTH_SCHEMES or not value:
        return f"Unknown Authorization scheme ({scheme or 'empty'})", None
    return f"Authorization: {scheme}", value


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


@router.post(
    "/orders",
    response_model=OrderOut,
    status_code=201,
    dependencies=[Depends(order_rate_limit)],
)
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
        raise HTTPException(status_code=404, detail="Order not found") from exc
    order = payment_service.get_order(db, order_uuid, current)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
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
    được cấu hình ở backend và nhập vào phần bảo mật của webhook trên SePay.
    Với phương thức "API Key", SePay gửi `Authorization: Apikey <key>` (không
    phải Bearer); cũng nhận thêm `Authorization: Bearer <key>` và header
    `X-Webhook-Secret`.

    Luôn trả 2xx khi secret hợp lệ để SePay không retry vô hạn; giao dịch
    không khớp đơn nào chỉ được log, không ảnh hưởng dữ liệu.
    """
    configured_secret = get_settings().sepay_webhook_secret.strip()
    if not configured_secret:
        raise HTTPException(
            status_code=503,
            detail="SEPAY_WEBHOOK_SECRET is not configured on the backend",
        )

    scheme, received_secret = _parse_authorization(authorization)
    received_secret = x_webhook_secret or received_secret
    if not received_secret or not secrets.compare_digest(received_secret, configured_secret):
        # Chỉ log dạng băm của giá trị NHẬN ĐƯỢC (đủ để đối chiếu khi cấu hình
        # sai) — không log gì về secret đang cấu hình, tránh rò rỉ qua file log.
        logger.warning(
            "SePay webhook auth failed: header=%s | received len=%d sha=%s",
            "X-Webhook-Secret" if x_webhook_secret else scheme,
            len(received_secret or ""),
            _fingerprint(received_secret or ""),
        )
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    if not payload:
        raise HTTPException(status_code=400, detail="Webhook payload must not be empty")

    result = payment_service.process_sepay_webhook(db, payload)
    logger.info("SePay webhook: %s", result)
    return {"status": "received", "result": result}
