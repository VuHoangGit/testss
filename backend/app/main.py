"""Điểm vào FastAPI: app factory, CORS, mapping AuthError → 401, mount router."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.security import AuthError


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    # CORS: cho phép localhost/127.0.0.1 mọi port (Flutter web dev chạy port
    # ngẫu nhiên) và cả IP tư nhân trong LAN (mở app trên điện thoại qua
    # http://<IP-máy>:port); origin công cộng khác chỉ nhận khi khai báo
    # CORS_ORIGINS.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=(
            r"https?://(localhost|127\.0\.0\.1"
            r"|192\.168\.\d{1,3}\.\d{1,3}"
            r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
            r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})"
            r"(:\d+)?"
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
