import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OcrPageOut(BaseModel):
    """Nội dung 1 trang. `source` = "text-layer" (PDF có sẵn chữ) hoặc "vision"."""

    page: int
    text: str
    source: str = "vision"


class OcrPartyOut(BaseModel):
    """Một bên tham gia tài liệu (bên A/bên B, người mua/người bán...)."""

    vai_tro: str | None = None
    ten: str | None = None
    ma_so: str | None = None


class OcrMoneyOut(BaseModel):
    """Tổng tiền: `so` giữ nguyên chuỗi như trên tài liệu (không đổi định dạng)."""

    so: str | None = None
    don_vi: str = "VND"


class OcrStructuredOut(BaseModel):
    """Trường dữ liệu theo schema CỐ ĐỊNH — khoá không đổi giữa các lần chạy."""

    loai_tai_lieu: str | None = None
    so_hieu: str | None = None
    ngay_ban_hanh: str | None = None
    cac_ben: list[OcrPartyOut] = Field(default_factory=list)
    tong_tien: OcrMoneyOut = Field(default_factory=OcrMoneyOut)
    thoi_han: str | None = None
    dieu_khoan_chinh: list[str] = Field(default_factory=list)
    # Trường AI khai "không chắc" — để người dùng đối soát thay vì tin ngay
    truong_khong_chac_chan: list[str] = Field(default_factory=list)


class OCRResult(BaseModel):
    """Kết quả OCR: văn bản từng trang + trường dữ liệu + cảnh báo hậu kiểm."""

    text: str
    # Dạng phẳng của `data` (tương thích client cũ)
    key_values: dict[str, str]
    pages: list[OcrPageOut] = Field(default_factory=list)
    data: OcrStructuredOut = Field(default_factory=OcrStructuredOut)
    warnings: list[str] = Field(default_factory=list)


class OcrRequest(BaseModel):
    """Tuỳ chọn OCR (không bắt buộc): loại tài liệu, ngôn ngữ, thuật ngữ riêng."""

    doc_type: str = Field(default="", max_length=100)
    language: str = Field(default="", max_length=100)
    glossary: str = Field(default="", max_length=500)


class TranslationRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    target_language: str = Field(default="English", min_length=2, max_length=50)
    # None/"" = tự phát hiện ngôn ngữ nguồn
    source_language: str | None = Field(default=None, max_length=50)


class TranslationResult(BaseModel):
    translation: str


class ExtractTextResult(BaseModel):
    """Nội dung văn bản trích từ tài liệu (PDF/Word/text) để hiển thị."""
    text: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4_000)
    document_ids: list[str] = Field(default_factory=list, max_length=20)


class ChatResult(BaseModel):
    answer: str
    # Hội thoại chứa vừa lưu câu hỏi + câu trả lời này
    conversation_id: uuid.UUID


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID | None = None
    title: str
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    created_at: datetime
