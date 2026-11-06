import io
import uuid

from app.core.config import get_settings
from app.models.document import Document
from app.models.user import User
from app.services import ai_service, ocr_service


def _login(client, make_token):
    token = make_token(sub="g-sub-1", email="user1@gmail.com", name="Nguyễn Văn A")
    # Warm: request đầu tiên qua /auth/me để dependency resolve+commit user local
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    return token


def test_chat_answers_using_owned_pdf(
    client, monkeypatch, make_token, db_session_factory
):
    token = _login(client, make_token)
    with db_session_factory() as db:
        user = db.query(User).one()
        document = Document(
            owner_id=user.id,
            original_name="guide.pdf",
            storage_key="guide.pdf",
            mime_type="application/pdf",
            size_bytes=10,
        )
        db.add(document)
        db.commit()
        document_id = str(document.id)

    monkeypatch.setattr(
        "app.api.v1.ai.storage_service.read_document_bytes",
        lambda storage_key: b"pdf bytes",
    )
    monkeypatch.setattr(
        "app.api.v1.ai.ai_service.extract_pdf_text",
        lambda data: "Tên sản phẩm: DocuVault",
    )
    monkeypatch.setattr(
        "app.api.v1.ai.ai_service.answer_question",
        lambda context, question: f"{question}: {context}",
    )

    response = client.post(
        "/api/v1/ai/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "Sản phẩm tên gì?", "document_ids": [document_id]},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Sản phẩm tên gì?: Tên sản phẩm: DocuVault"
    assert response.json()["conversation_id"]  # UUID của hội thoại vừa tạo


def test_chat_rejects_pdf_without_extractable_text(
    client, monkeypatch, make_token, db_session_factory
):
    token = _login(client, make_token)
    with db_session_factory() as db:
        user = db.query(User).one()
        document = Document(
            owner_id=user.id,
            original_name="scan.pdf",
            storage_key="scan.pdf",
            mime_type="application/pdf",
            size_bytes=10,
        )
        db.add(document)
        db.commit()
        document_id = str(document.id)

    monkeypatch.setattr(
        "app.api.v1.ai.storage_service.read_document_bytes",
        lambda storage_key: b"pdf bytes",
    )
    monkeypatch.setattr(
        "app.api.v1.ai.ai_service.extract_pdf_text",
        lambda data: "",
    )

    response = client.post(
        "/api/v1/ai/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "Có gì trong tài liệu?", "document_ids": [document_id]},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Select at least one PDF that contains text"


def test_chat_rejects_document_owned_by_another_user(
    client, monkeypatch, make_token, db_session_factory
):
    token = _login(client, make_token)
    with db_session_factory() as db:
        other_user = User(supabase_id="other", email="other@example.com")
        db.add(other_user)
        db.flush()
        document = Document(
            owner_id=other_user.id,
            original_name="private.pdf",
            storage_key=f"{uuid.uuid4()}.pdf",
            mime_type="application/pdf",
            size_bytes=10,
        )
        db.add(document)
        db.commit()
        document_id = str(document.id)

    response = client.post(
        "/api/v1/ai/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": "Đọc tài liệu này", "document_ids": [document_id]},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found"


# ---------------------------------------------------------------------------
# GET /ai/extract-text/{id} — trích văn bản hiển thị cho màn dịch vùng chọn


def _make_document(db_session_factory, *, name: str, mime_type: str, storage_key=None):
    with db_session_factory() as db:
        user = db.query(User).one()
        document = Document(
            owner_id=user.id,
            original_name=name,
            storage_key=storage_key or f"{uuid.uuid4()}-{name}",
            mime_type=mime_type,
            size_bytes=10,
        )
        db.add(document)
        db.commit()
        return str(document.id)


def test_extract_text_requires_auth(client):
    response = client.get(f"/api/v1/ai/extract-text/{uuid.uuid4()}")
    assert response.status_code == 401


def test_extract_text_returns_pdf_text(
    client, monkeypatch, make_token, db_session_factory
):
    token = _login(client, make_token)
    document_id = _make_document(
        db_session_factory, name="hop-dong.pdf", mime_type="application/pdf"
    )
    monkeypatch.setattr(
        "app.api.v1.ai.storage_service.read_document_bytes",
        lambda storage_key: b"pdf bytes",
    )
    monkeypatch.setattr(
        "app.api.v1.ai.ai_service.extract_pdf_text",
        lambda data: "Điều 1: Hợp đồng có hiệu lực từ hôm nay",
    )

    response = client.get(
        f"/api/v1/ai/extract-text/{document_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"text": "Điều 1: Hợp đồng có hiệu lực từ hôm nay"}


def test_extract_text_decodes_markdown_file(
    client, monkeypatch, make_token, db_session_factory
):
    token = _login(client, make_token)
    document_id = _make_document(
        db_session_factory, name="srs.md", mime_type="text/markdown"
    )
    monkeypatch.setattr(
        "app.api.v1.ai.storage_service.read_document_bytes",
        lambda storage_key: "# SRS\nMô tả chức năng".encode(),
    )

    response = client.get(
        f"/api/v1/ai/extract-text/{document_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"text": "# SRS\nMô tả chức năng"}


def test_extract_text_unsupported_mime_returns_415(
    client, monkeypatch, make_token, db_session_factory
):
    token = _login(client, make_token)
    document_id = _make_document(
        db_session_factory, name="anh.png", mime_type="image/png"
    )

    response = client.get(
        f"/api/v1/ai/extract-text/{document_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 415
    assert "cannot be read" in response.json()["detail"]


def test_extract_text_empty_pdf_returns_422(
    client, monkeypatch, make_token, db_session_factory
):
    token = _login(client, make_token)
    document_id = _make_document(
        db_session_factory, name="scan.pdf", mime_type="application/pdf"
    )
    monkeypatch.setattr(
        "app.api.v1.ai.storage_service.read_document_bytes",
        lambda storage_key: b"pdf bytes",
    )
    monkeypatch.setattr(
        "app.api.v1.ai.ai_service.extract_pdf_text",
        lambda data: "",
    )

    response = client.get(
        f"/api/v1/ai/extract-text/{document_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /ai/translate — nhận thêm source_language


def test_translate_forwards_source_language(client, monkeypatch, make_token):
    token = _login(client, make_token)
    captured = {}

    def fake_translate(text, target_language, source_language=None):
        captured["args"] = (text, target_language, source_language)
        return f"[{target_language}] {text}"

    monkeypatch.setattr(
        "app.api.v1.ai.ai_service.translate_selection", fake_translate
    )

    response = client.post(
        "/api/v1/ai/translate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "text": "Xin chào",
            "target_language": "English",
            "source_language": "Vietnamese",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"translation": "[English] Xin chào"}
    assert captured["args"] == ("Xin chào", "English", "Vietnamese")


def test_translate_defaults_source_to_auto(client, monkeypatch, make_token):
    token = _login(client, make_token)
    captured = {}

    def fake_translate(text, target_language, source_language=None):
        captured["source"] = source_language
        return "Hello"

    monkeypatch.setattr(
        "app.api.v1.ai.ai_service.translate_selection", fake_translate
    )

    response = client.post(
        "/api/v1/ai/translate",
        headers={"Authorization": f"Bearer {token}"},
        json={"text": "Xin chào", "target_language": "English"},
    )

    assert response.status_code == 200
    assert captured["source"] is None


# ---------------------------------------------------------------------------
# POST /ai/ocr/{id} — pipeline OCR theo trang + cảnh báo hậu kiểm


def test_ocr_returns_pages_structured_data_and_warnings(
    client, monkeypatch, make_token, db_session_factory
):
    token = _login(client, make_token)
    document_id = _make_document(
        db_session_factory, name="hop-dong.pdf", mime_type="application/pdf"
    )
    monkeypatch.setattr(
        "app.api.v1.ai.storage_service.read_document_bytes",
        lambda storage_key: b"pdf bytes",
    )
    monkeypatch.setattr(
        "app.api.v1.ai.ocr_service.ocr_document_bytes",
        lambda data, mime_type, name, options: ocr_service.OcrOutcome(
            pages=[
                ocr_service.OcrPage(page=1, text="Trang một", source="text-layer"),
                ocr_service.OcrPage(page=2, text="Trang hai", source="vision"),
            ],
            structured={
                **ocr_service.empty_structured(),
                "so_hieu": "01/HĐ",
                "tong_tien": {"so": "1250000", "don_vi": "VND"},
            },
            warnings=["1 spot(s) marked as unreadable ([?]/[lost text])"],
        ),
    )

    response = client.post(
        f"/api/v1/ai/ocr/{document_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [page["page"] for page in body["pages"]] == [1, 2]
    assert [page["source"] for page in body["pages"]] == ["text-layer", "vision"]
    assert "--- Trang 1 ---" in body["text"]
    assert body["data"]["so_hieu"] == "01/HĐ"
    assert body["key_values"]["tong_tien"] == "1250000 VND"
    assert body["warnings"]


def test_ocr_forwards_document_hints_from_body(
    client, monkeypatch, make_token, db_session_factory
):
    token = _login(client, make_token)
    document_id = _make_document(
        db_session_factory, name="hoa-don.pdf", mime_type="application/pdf"
    )
    captured = {}

    def fake_ocr(data, mime_type, name, options):
        captured["options"] = options
        return ocr_service.OcrOutcome(
            pages=[ocr_service.OcrPage(page=1, text="Nội dung", source="text-layer")]
        )

    monkeypatch.setattr(
        "app.api.v1.ai.storage_service.read_document_bytes", lambda storage_key: b"pdf"
    )
    monkeypatch.setattr("app.api.v1.ai.ocr_service.ocr_document_bytes", fake_ocr)

    response = client.post(
        f"/api/v1/ai/ocr/{document_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "doc_type": "hoá đơn",
            "language": "tiếng Việt",
            "glossary": "Công ty ABC",
        },
    )

    assert response.status_code == 200, response.text
    assert captured["options"].doc_type == "hoá đơn"
    assert captured["options"].language == "tiếng Việt"
    assert captured["options"].glossary == "Công ty ABC"


def test_ocr_failure_refunds_credit(
    client, monkeypatch, make_token, db_session_factory
):
    token = _login(client, make_token)
    document_id = _make_document(
        db_session_factory, name="hong.pdf", mime_type="application/pdf"
    )
    monkeypatch.setattr(
        "app.api.v1.ai.storage_service.read_document_bytes", lambda storage_key: b"pdf"
    )
    monkeypatch.setattr(
        "app.api.v1.ai.ocr_service.ocr_document_bytes",
        lambda data, mime_type, name, options: (_ for _ in ()).throw(
            ai_service.AIServiceError("No page of the document could be read.")
        ),
    )

    response = client.post(
        f"/api/v1/ai/ocr/{document_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 503
    assert "No page of the document could be read" in response.json()["detail"]
    # Hoàn đủ credit của lượt hỏng
    credits = client.get(
        "/api/v1/payments/credits", headers={"Authorization": f"Bearer {token}"}
    )
    assert credits.json()["total"] == get_settings().credit_monthly_free


# ---------------------------------------------------------------------------
# POST /ai/ocr/{id}/word — file .docx phải giữ cấu trúc, không phải chữ thô


def test_ocr_word_export_keeps_heading_structure(
    client, monkeypatch, make_token, db_session_factory
):
    """Bản Word tải về có Heading thật (mục lục dựng được) + bảng thật."""
    from docx import Document as OpenDocument

    token = _login(client, make_token)
    document_id = _make_document(
        db_session_factory, name="hop-dong.pdf", mime_type="application/pdf"
    )
    monkeypatch.setattr(
        "app.api.v1.ai.storage_service.read_document_bytes",
        lambda storage_key: b"pdf bytes",
    )
    monkeypatch.setattr(
        "app.api.v1.ai.ocr_service.ocr_document_bytes",
        lambda data, mime_type, name, options: ocr_service.OcrOutcome(
            pages=[
                ocr_service.OcrPage(
                    page=1,
                    text=(
                        "# ĐIỀU KHOẢN CHUNG\n"
                        "## Điều 1. Phạm vi\n"
                        "- Bên A thanh toán **1.250.000 VND**\n"
                        "| Khoản | Số tiền |\n|---|---|\n| Phí | 1.250.000 |\n"
                    ),
                    source="vision",
                )
            ]
        ),
    )

    response = client.post(
        f"/api/v1/ai/ocr/{document_id}/word",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    exported = OpenDocument(io.BytesIO(response.content))
    styles = [paragraph.style.name for paragraph in exported.paragraphs]
    assert "Heading 1" in styles
    assert "Heading 2" in styles
    # tài liệu có ≥ 2 tiêu đề → chèn mục lục (field TOC) ở đầu file
    assert "Mục lục" in [paragraph.text for paragraph in exported.paragraphs]
    assert 'TOC \\o "1-3"' in exported.element.xml
    assert len(exported.tables) == 1
    assert exported.tables[0].cell(1, 1).text == "1.250.000"
    # dấu Markdown không lọt ra file
    body = "\n".join(paragraph.text for paragraph in exported.paragraphs)
    assert "##" not in body
    assert "**" not in body
