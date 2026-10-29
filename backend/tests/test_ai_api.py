import uuid

from app.models.document import Document
from app.models.user import User


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
    assert response.json()["detail"] == "Chọn ít nhất một PDF có nội dung văn bản"


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
    assert response.json()["detail"] == "Không tìm thấy tài liệu"


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
    assert "Chưa hỗ trợ" in response.json()["detail"]


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
