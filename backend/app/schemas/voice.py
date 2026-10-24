"""Schema API ra lệnh bằng giọng nói.

Client gửi transcript cùng ngữ cảnh app (danh sách thư mục/tài liệu đang có)
để backend chuyển cho Gemini chọn action. Id chỉ dùng để client resolve lại
tên → id; backend KHÔNG gửi id lên Gemini (chống bịa id).
"""

from pydantic import BaseModel, Field


class VoiceFolder(BaseModel):
    id: str
    name: str


class VoiceDocument(BaseModel):
    id: str
    name: str
    mime_type: str = ""


class VoiceAppContext(BaseModel):
    current_tab: str | None = None
    folders: list[VoiceFolder] = Field(default_factory=list, max_length=100)
    documents: list[VoiceDocument] = Field(default_factory=list, max_length=500)


class VoiceCommandRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=1000)
    context: VoiceAppContext = Field(default_factory=VoiceAppContext)
    # Id phiên voice trên client — server dùng để giữ ngữ cảnh hội thoại
    session_id: str = Field(min_length=4, max_length=64)


class VoiceCommandResponse(BaseModel):
    # None khi Gemini chỉ trả lời text (hỏi lại/chào hỏi) hoặc action không hợp lệ
    action: str | None = None
    params: dict[str, object] = Field(default_factory=dict)
    reply: str
