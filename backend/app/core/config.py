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
    # Host hợp lệ trong header `Host` (chống DNS rebinding), phân cách bằng dấu
    # phẩy; "*" = không kiểm tra (mặc định cho dev). Production PHẢI khai báo
    # đúng domain thật, nếu không app sẽ log cảnh báo lúc khởi động.
    trusted_hosts: str = "*"
    # Thư mục chứa file tài liệu upload (Sprint 2). Rỗng = backend/storage/documents
    documents_dir: str = ""
    # Giới hạn dung lượng 1 file upload (MB)
    max_upload_mb: int = 50
    # Loại file được phép upload (theo đuôi, phân cách bằng dấu phẩy). MIME do
    # server quyết định theo bảng này, KHÔNG tin content_type client gửi lên.
    allowed_upload_types: str = (
        "pdf,doc,docx,xls,xlsx,ppt,pptx,txt,md,jpg,jpeg,png,gif,zip"
    )
    # Tổng dung lượng tài liệu tối đa của 1 user (MB); 0 = không giới hạn
    user_storage_quota_mb: int = 1024
    # Giới hạn tần suất gọi API (theo user, cửa sổ trượt 60 giây). Tắt bằng
    # RATE_LIMIT_ENABLED=false (test tự tắt trong conftest).
    rate_limit_enabled: bool = True
    rate_limit_ai_per_minute: int = 60
    rate_limit_upload_per_minute: int = 30
    rate_limit_orders_per_minute: int = 20
    # AI qua API tương thích Anthropic Messages (vd GLM của z.ai).
    # Đổi model chỉ cần sửa ANTHROPIC_MODEL trong .env, không sửa code.
    anthropic_auth_token: str = ""
    anthropic_base_url: str = "https://api.z.ai/api/anthropic"
    anthropic_model: str = "glm-4.6"
    # Model đọc ẢNH cho OCR trang scan. Rỗng = dùng chung ANTHROPIC_MODEL; cần
    # đặt riêng khi model văn bản không nhận block ảnh (vd key z.ai chỉ có
    # nhóm mg::text thì OCR trang scan báo lỗi cấu hình rõ ràng).
    ocr_vision_model: str = ""
    anthropic_timeout_seconds: int = 90
    # OCR: mỗi trang là 1 lượt gọi AI. Giới hạn số trang mỗi lần OCR để chặn
    # tài liệu quá dài làm treo request (phần dư bị bỏ và có cảnh báo).
    ocr_max_pages: int = 20
    # DPI render trang PDF scan trước khi gửi AI (200 DPI ≈ cạnh dài 1654px/trang A4).
    ocr_dpi: int = 200
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
    def is_dev(self) -> bool:
        """True khi chạy dev/test — bật các nới lỏng KHÔNG được dùng ở production."""
        return self.environment.strip().lower() in {"dev", "local", "development", "test"}

    @property
    def allowed_email_domain_list(self) -> list[str]:
        return [x.strip().lower() for x in self.allowed_email_domains.split(",") if x.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def allowed_upload_type_list(self) -> list[str]:
        """Phần mở rộng file được phép upload, viết thường, không có dấu chấm."""
        return [
            item.strip().lower().lstrip(".")
            for item in self.allowed_upload_types.split(",")
            if item.strip()
        ]

    @property
    def trusted_host_list(self) -> list[str]:
        return [x.strip() for x in self.trusted_hosts.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
