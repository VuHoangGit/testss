"""Điểm vào FastAPI: app factory, CORS, mapping AuthError → 401, mount router."""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.security import AuthError

logger = logging.getLogger(__name__)

# Origin dev được tự động chấp nhận: localhost/127.0.0.1 mọi port (Flutter web
# dev chạy port ngẫu nhiên) và IP tư nhân trong LAN (mở app trên điện thoại qua
# http://<IP-máy>:port). CHỈ bật khi environment = dev — production phải khai
# báo CORS_ORIGINS tường minh.
_DEV_ORIGIN_REGEX = (
    r"https?://(localhost|127\.0\.0\.1"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})"
    r"(:\d+)?"
)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    if not settings.is_dev and "*" in settings.trusted_host_list:
        logger.warning(
            "TRUSTED_HOSTS đang là '*' trong môi trường %s — hãy khai báo domain thật",
            settings.environment,
        )

    # Chống DNS rebinding: chỉ nhận request có header Host thuộc danh sách.
    # "*" = không kiểm tra (dev).
    trusted_hosts = settings.trusted_host_list
    if trusted_hosts and trusted_hosts != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts)

    cors_options: dict[str, object] = {
        "allow_origins": settings.cors_origin_list,
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }
    if settings.is_dev:
        cors_options["allow_origin_regex"] = _DEV_ORIGIN_REGEX
    app.add_middleware(CORSMiddleware, **cors_options)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        """Gắn header bảo mật cho mọi response (chặn MIME sniffing, nhúng frame, HSTS)."""
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if not settings.is_dev:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    @app.exception_handler(AuthError)
    async def auth_error_handler(request: Request, exc: AuthError) -> JSONResponse:
        return JSONResponse(status_code=401, content={"detail": exc.message})

    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health")
    def health() -> dict[str, object]:
        s = get_settings()
        return {
            "status": "ok",
            "app": s.app_name,
            "ai_configured": bool(s.anthropic_auth_token.strip()),
        }

    return app


app = create_app()
