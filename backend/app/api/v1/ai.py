"""OCR, Key-Value, dịch vùng chọn và chatbot tài liệu."""

import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.api.deps import CurrentUser, DbSession
from app.models.document import Document
from app.schemas.ai import ChatRequest, ChatResult, OCRResult, TranslationRequest, TranslationResult
from app.services import ai_service, storage_service

router = APIRouter(prefix="/ai", tags=["ai"])


def _owned_document(db, document_id: uuid.UUID, user_id) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.owner_id != user_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    return document


@router.post("/ocr/{document_id}", response_model=OCRResult)
def ocr(document_id: uuid.UUID, db: DbSession, current: CurrentUser) -> OCRResult:
    _, user = current
    document = _owned_document(db, document_id, user.id)
    try:
        text = ai_service.ocr_document(
            storage_service.read_document_bytes(document.storage_key), document.mime_type
        )
        return OCRResult(text=text, key_values=ai_service.extract_key_values(text))
    except ai_service.AIServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/ocr/{document_id}/word")
def ocr_word(document_id: uuid.UUID, db: DbSession, current: CurrentUser) -> Response:
    _, user = current
    document = _owned_document(db, document_id, user.id)
    try:
        text = ai_service.ocr_document(
            storage_service.read_document_bytes(document.storage_key), document.mime_type
        )
        content = ai_service.make_word_document(text)
    except ai_service.AIServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{document.original_name}.docx"'},
    )


@router.post("/translate", response_model=TranslationResult)
def translate(body: TranslationRequest, current: CurrentUser) -> TranslationResult:
    try:
        return TranslationResult(
            translation=ai_service.translate_selection(body.text, body.target_language)
        )
    except ai_service.AIServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/chat", response_model=ChatResult)
def chat(body: ChatRequest, db: DbSession, current: CurrentUser) -> ChatResult:
    _, user = current
    try:
        ids = [uuid.UUID(value) for value in body.document_ids]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="document_ids không hợp lệ") from exc
    context_parts: list[str] = []
    for document_id in ids:
        document = _owned_document(db, document_id, user.id)
        if document.mime_type == "application/pdf":
            text = ai_service.extract_pdf_text(
                storage_service.read_document_bytes(document.storage_key)
            )
            if text:
                context_parts.append(text)
    if not context_parts:
        raise HTTPException(status_code=400, detail="Chọn ít nhất một PDF có nội dung văn bản")
    try:
        answer = ai_service.answer_question("\n\n".join(context_parts), body.question)
        return ChatResult(answer=answer)
    except ai_service.AIServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
