"""Cấu hình ứng dụng đọc từ biến môi trường / file .env.

Không hardcode secret: JWT_SECRET và GOOGLE_CLIENT_IDS là bắt buộc,
thiếu thì app từ chối khởi động (fail fast).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "DocuVault API"
    environment: str = "dev"

    # SQLAlchemy 2.0 + psycopg3 (sync). Dev không có Docker có thể dùng sqlite:///...
    database_url: str = "postgresql+psycopg://docuvault:docuvault@localhost:5432/docuvault"

    # JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "docuvault"
    access_token_minutes: int = 15
    refresh_token_days: int = 30

    # Danh sách OAuth client ID của Google, phân cách bằng dấu phẩy
    google_client_ids: str
    # Rỗng = mở cho mọi account Google (EC-35)
    allowed_email_domains: str = ""
    # Origin được phép gọi API (CORS), phân cách bằng dấu phẩy; rỗng = tắt
    cors_origins: str = ""
    # Bật POST /auth/dev (đăng nhập nhanh không cần Google) — CHỈ cho dev/demo
    allow_dev_login: bool = False
    # Thư mục chứa file tài liệu upload (Sprint 2). Rỗng = backend/storage/documents
    documents_dir: str = ""
    # Giới hạn dung lượng 1 file upload (MB)
    max_upload_mb: int = 50
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: int = 60

    @property
    def google_client_id_list(self) -> list[str]:
        return [x.strip() for x in self.google_client_ids.split(",") if x.strip()]

    @property
    def allowed_email_domain_list(self) -> list[str]:
        return [x.strip().lower() for x in self.allowed_email_domains.split(",") if x.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
