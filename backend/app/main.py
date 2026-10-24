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

    # CORS: luôn cho phép localhost/127.0.0.1 mọi port (Flutter web dev chạy port
    # ngẫu nhiên); origin khác chỉ nhận khi khai báo CORS_ORIGINS.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
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
        # Đọc lúc request để test có thể bật/tắt allow_dev_login động
        s = get_settings()
        return {
            "status": "ok",
            "app": s.app_name,
            "dev_login": s.allow_dev_login,
            "ai_configured": bool(s.gemini_api_key.strip()),
        }

    return app


app = create_app()
