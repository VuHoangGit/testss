"""Cấu hình ứng dụng đọc từ biến môi trường / file .env.

Đăng nhập do Supabase Auth quản lý: SUPABASE_URL là bắt buộc, thiếu thì app
từ chối khởi động (fail fast). Anon key chỉ nằm phía client, backend không cần.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "DocuVault API"
    environment: str = "dev"

    # SQLAlchemy 2.0 + psycopg3 (sync). Dev không có Docker có thể dùng sqlite:///...
    database_url: str = "postgresql+psycopg://docuvault:docuvault@localhost:5432/docuvault"

    # Supabase Auth: URL project (vd https://abcdef.supabase.co).
    # Backend verify access token qua JWKS của project này.
    supabase_url: str
    # Rỗng = mở cho mọi account (EC-35)
    allowed_email_domains: str = ""
    # Origin được phép gọi API (CORS), phân cách bằng dấu phẩy; rỗng = tắt
    cors_origins: str = ""
    # Thư mục chứa file tài liệu upload (Sprint 2). Rỗng = backend/storage/documents
    documents_dir: str = ""
    # Giới hạn dung lượng 1 file upload (MB)
    max_upload_mb: int = 50
    # AI qua API tương thích Anthropic Messages (vd GLM của z.ai).
    # Đổi model chỉ cần sửa ANTHROPIC_MODEL trong .env, không sửa code.
    anthropic_auth_token: str = ""
    anthropic_base_url: str = "https://api.z.ai/api/anthropic"
    anthropic_model: str = "glm-4.6"
    anthropic_timeout_seconds: int = 90
    # Secret dùng để xác thực request webhook từ SePay.
    sepay_webhook_secret: str = ""
    # Tài khoản nhận tiền (từ trang quản lý SePay) — dùng dựng QR VietQR.
    # Rỗng = chưa cấu hình: đơn vẫn tạo được nhưng không có ảnh QR.
    sepay_bank_account: str = ""
    sepay_bank_bin: str = "MB"  # mã ngân hàng cho VietQR (MB Bank)
    sepay_account_name: str = ""

    # Credit AI: free mỗi tháng và giá mỗi lượt gọi tính năng AI.
    credit_monthly_free: int = 300
    credit_cost_ai: int = 50

    @property
    def supabase_issuer(self) -> str:
        """Giá trị `iss` trong access token do Supabase cấp."""
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def supabase_jwks_url(self) -> str:
        """Endpoint JWKS dùng verify chữ ký token."""
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def allowed_email_domain_list(self) -> list[str]:
        return [x.strip().lower() for x in self.allowed_email_domains.split(",") if x.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
