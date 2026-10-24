import uuid

from app.models.document import Document
from app.models.user import User


def _login(client, monkeypatch, make_identity):
    monkeypatch.setattr(
        "app.api.v1.auth.verify_google_id_token",
        lambda token: make_identity(),
    )
    response = client.post(
        "/api/v1/auth/google",
        json={"id_token": "fake-id-token-do-google-cap-du-dai-20-ky-tu"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_chat_answers_using_owned_pdf(
    client, monkeypatch, make_identity, db_session_factory
):
    token = _login(client, monkeypatch, make_identity)
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
    assert response.json() == {
        "answer": "Sản phẩm tên gì?: Tên sản phẩm: DocuVault"
    }


def test_chat_rejects_pdf_without_extractable_text(
    client, monkeypatch, make_identity, db_session_factory
):
    token = _login(client, monkeypatch, make_identity)
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
    client, monkeypatch, make_identity, db_session_factory
):
    token = _login(client, monkeypatch, make_identity)
    with db_session_factory() as db:
        other_user = User(google_sub="other", email="other@example.com")
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
