"""OCR, Key-Value, dịch vùng chọn, chatbot tài liệu + lưu hội thoại chat."""

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession, ai_rate_limit
from app.models.conversation import AiConversation
from app.models.document import Document
from app.models.message import AiMessage
from app.schemas.ai import (
    ChatRequest,
    ChatResult,
    ConversationOut,
    ExtractTextResult,
    MessageOut,
    OcrPageOut,
    OcrRequest,
    OCRResult,
    OcrStructuredOut,
    TranslationRequest,
    TranslationResult,
)
from app.schemas.voice import VoiceCommandRequest, VoiceCommandResponse
from app.services import (
    ai_service,
    credit_service,
    ocr_service,
    pdf_to_docx_service,
    storage_service,
    voice_command_service,
)

# Mọi endpoint AI đều tốn tiền gọi nhà cung cấp AI → giới hạn tần suất ở mức
# router để không endpoint nào bị bỏ sót khi thêm route mới.
router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(ai_rate_limit)])


def _charge_ai(db, user) -> None:
    """Trừ 50 credit trước mỗi lượt gọi AI; hết credit → 402 (kèm hướng dẫn)."""
    try:
        credit_service.charge(db, user)
    except credit_service.InsufficientCredits as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc


def _attachment_header(filename: str) -> str:
    """Dựng `Content-Disposition` an toàn từ tên file do người dùng đặt.

    `original_name` là dữ liệu client gửi lên — chèn thẳng vào header thì dấu
    `"`/CR/LF có thể phá header hoặc chèn thêm tham số. Tên ASCII được lọc, tên
    đầy đủ (tiếng Việt) đi qua `filename*` đã percent-encode.
    """
    safe_ascii = (
        "".join(
            ch for ch in filename if ch.isascii() and ch.isprintable() and ch not in '"\\;'
        ).strip()
        or "document"
    )
    return f"attachment; filename=\"{safe_ascii}\"; filename*=UTF-8''{quote(filename, safe='')}"


def _owned_document(db, document_id: uuid.UUID, user_id) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.owner_id != user_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def _own_conversation(db, conversation_id: uuid.UUID, user_id) -> AiConversation:
    conversation = db.get(AiConversation, conversation_id)
    if conversation is None or conversation.user_id != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def _ocr_document(document: Document, body: OcrRequest | None) -> ocr_service.OcrOutcome:
    """Chạy OCR cho 1 tài liệu; tuỳ chọn client ghi đè loại/ngôn ngữ/thuật ngữ."""
    options = ocr_service.default_options()
    if body is not None:
        options = dataclasses.replace(
            options,
            doc_type=body.doc_type.strip() or options.doc_type,
            language=body.language.strip() or options.language,
            glossary=body.glossary.strip(),
        )
    return ocr_service.ocr_document_bytes(
        storage_service.read_document_bytes(document.storage_key),
        document.mime_type,
        document.original_name,
        options,
    )


@router.post("/ocr/{document_id}", response_model=OCRResult)
def ocr(
    document_id: uuid.UUID,
    db: DbSession,
    current: CurrentUser,
    body: OcrRequest | None = None,
) -> OCRResult:
    """OCR tài liệu (từng trang) → văn bản + trường dữ liệu + cảnh báo đối soát."""
    user = current
    document = _owned_document(db, document_id, user.id)
    _charge_ai(db, user)
    try:
        outcome = _ocr_document(document, body)
    except ai_service.AIServiceError as exc:
        credit_service.refund(db, user)  # lỗi AI — hoàn credit lượt này
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return OCRResult(
        text=outcome.text,
        key_values=outcome.key_values,
        pages=[OcrPageOut(page=p.page, text=p.text, source=p.source) for p in outcome.pages],
        data=OcrStructuredOut(**outcome.structured),
        warnings=outcome.warnings,
    )


@router.post("/ocr/{document_id}/word")
def ocr_word(document_id: uuid.UUID, db: DbSession, current: CurrentUser) -> Response:
    user = current
    document = _owned_document(db, document_id, user.id)
    try:
        if document.mime_type == "application/pdf":
            pdf_bytes = storage_service.read_document_bytes(document.storage_key)
            if pdf_bytes.startswith(b"%PDF"):
                content = pdf_to_docx_service.export_pdf_to_docx(
                    pdf_bytes,
                    title=document.original_name,
                )
            else:
                _charge_ai(db, user)
                content = ai_service.make_word_document(
                    _ocr_document(document, None).text,
                    title=document.original_name,
                )
        else:
            _charge_ai(db, user)
            content = ai_service.make_word_document(
                _ocr_document(document, None).text,
                title=document.original_name,
            )
    except (ValueError, RuntimeError, ai_service.AIServiceError) as exc:
        if document.mime_type != "application/pdf":
            credit_service.refund(db, user)
        if isinstance(exc, ai_service.AIServiceError):
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": _attachment_header(f"{document.original_name}.docx"),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/extract-text/{document_id}", response_model=ExtractTextResult)
def extract_text(document_id: uuid.UUID, db: DbSession, current: CurrentUser) -> ExtractTextResult:
    """Trích nội dung văn bản của tài liệu để hiển thị/dịch vùng chọn.

    Chạy cục bộ (pypdf/python-docx/decode), không tốn lượt gọi AI.
    """
    user = current
    document = _owned_document(db, document_id, user.id)
    if not ai_service.is_text_extractable(document.mime_type, document.original_name):
        raise HTTPException(
            status_code=415,
            detail=("This file type cannot be read (supported: PDF, Word, txt/md and plain text)"),
        )
    try:
        text = ai_service.extract_document_text(
            storage_service.read_document_bytes(document.storage_key),
            document.mime_type,
            document.original_name,
        )
    except ai_service.AIServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not text:
        raise HTTPException(
            status_code=422,
            detail="Could not extract text from the file (scanned PDF? Use OCR instead)",
        )
    return ExtractTextResult(text=text)


@router.post("/translate", response_model=TranslationResult)
def translate(body: TranslationRequest, db: DbSession, current: CurrentUser) -> TranslationResult:
    user = current
    source = body.source_language or None
    _charge_ai(db, user)
    try:
        return TranslationResult(
            translation=ai_service.translate_selection(
                body.text, body.target_language, source_language=source
            )
        )
    except ai_service.AIServiceError as exc:
        credit_service.refund(db, user)
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/chat", response_model=ChatResult)
def chat(body: ChatRequest, db: DbSession, current: CurrentUser) -> ChatResult:
    user = current
    try:
        ids = [uuid.UUID(value) for value in body.document_ids]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid document_ids") from exc
    context_parts: list[str] = []
    documents: list[Document] = []
    for document_id in ids:
        document = _owned_document(db, document_id, user.id)
        documents.append(document)
        if document.mime_type == "application/pdf":
            text = ai_service.extract_pdf_text(
                storage_service.read_document_bytes(document.storage_key)
            )
            if text:
                context_parts.append(text)
    if not context_parts:
        raise HTTPException(status_code=400, detail="Select at least one PDF that contains text")
    _charge_ai(db, user)
    try:
        answer = ai_service.answer_question("\n\n".join(context_parts), body.question)
    except ai_service.AIServiceError as exc:
        credit_service.refund(db, user)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Lưu hội thoại: gắn với tài liệu đầu tiên, dùng lại hội thoại mới nhất
    # của tài liệu đó (UI hiện giữ 1 luồng chat/tài liệu). AI lỗi thì KHÔNG
    # lưu gì (phần trên đã raise trước khi đến đây).
    primary = documents[0]
    conversation = db.scalars(
        select(AiConversation)
        .where(
            AiConversation.document_id == primary.id,
            AiConversation.user_id == user.id,
        )
        .order_by(AiConversation.updated_at.desc())
        .limit(1)
    ).first()
    if conversation is None:
        conversation = AiConversation(
            user_id=user.id,
            document_id=primary.id,
            title=body.question[:255],
        )
        db.add(conversation)
        db.flush()
    # Câu trả lời lệch 1µs so với câu hỏi → sort theo created_at luôn đúng thứ tự
    now = datetime.now(UTC)
    db.add(
        AiMessage(
            conversation_id=conversation.id,
            role="user",
            content=body.question,
            created_at=now,
        )
    )
    db.add(
        AiMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            created_at=now + timedelta(microseconds=1),
        )
    )
    conversation.updated_at = func.now()
    db.commit()
    return ChatResult(answer=answer, conversation_id=conversation.id)


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    db: DbSession,
    current: CurrentUser,
    document_id: uuid.UUID | None = None,
) -> list[ConversationOut]:
    """Danh sách hội thoại chat của user; `document_id` để lọc theo tài liệu."""
    user = current
    stmt = select(AiConversation).where(AiConversation.user_id == user.id)
    if document_id is not None:
        document = _owned_document(db, document_id, user.id)
        stmt = stmt.where(AiConversation.document_id == document.id)
    return list(db.scalars(stmt.order_by(AiConversation.updated_at.desc())))


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(
    conversation_id: uuid.UUID, db: DbSession, current: CurrentUser
) -> list[MessageOut]:
    """Tin nhắn của 1 hội thoại theo thứ tự gửi."""
    user = current
    conversation = _own_conversation(db, conversation_id, user.id)
    stmt = (
        select(AiMessage)
        .where(AiMessage.conversation_id == conversation.id)
        .order_by(AiMessage.created_at, AiMessage.id)
    )
    return list(db.scalars(stmt))


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: uuid.UUID, db: DbSession, current: CurrentUser
) -> dict[str, str]:
    user = current
    conversation = _own_conversation(db, conversation_id, user.id)
    db.delete(conversation)
    db.commit()
    return {"detail": "Conversation deleted"}


@router.post("/voice-command", response_model=VoiceCommandResponse)
def voice_command(body: VoiceCommandRequest, current: CurrentUser) -> VoiceCommandResponse:
    """Phân tích lệnh giọng nói thành action; việc thực thi nằm ở client."""
    try:
        return voice_command_service.interpret(
            transcript=body.transcript, context=body.context, session_id=body.session_id
        )
    except voice_command_service.VoiceCommandError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
