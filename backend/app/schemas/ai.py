from pydantic import BaseModel, Field


class OCRResult(BaseModel):
    text: str
    key_values: dict[str, str]


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
