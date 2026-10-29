"""Test lưu trữ hội thoại AI: ai_conversations/ai_messages, quyền truy cập
theo user, cascade khi xóa tài liệu."""

import uuid

from app.models.conversation import AiConversation
from app.models.document import Document
from app.models.message import AiMessage
from app.models.user import User


def _login(client, make_token):
    token = make_token(sub="g-sub-1", email="user1@gmail.com", name="Nguyễn Văn A")
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    return token


def _make_document(db_session_factory, *, owner_id, name="guide.pdf"):
    with db_session_factory() as db:
        document = Document(
            owner_id=owner_id,
            original_name=name,
            storage_key=f"{uuid.uuid4()}-{name}",
            mime_type="application/pdf",
            size_bytes=10,
        )
        db.add(document)
        db.commit()
        return str(document.id)


def _mock_ai_ok(monkeypatch, answer="Câu trả lời mẫu"):
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
        lambda context, question: answer,
    )


def _chat(client, token, document_id, question="Sản phẩm tên gì?"):
    return client.post(
        "/api/v1/ai/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"question": question, "document_ids": [document_id]},
    )


def test_chat_creates_conversation_and_messages(
    client, monkeypatch, make_token, db_session_factory
):
    token = _login(client, make_token)
    with db_session_factory() as db:
        user = db.query(User).one()
    document_id = _make_document(db_session_factory, owner_id=user.id)
    _mock_ai_ok(monkeypatch)

    resp = _chat(client, token, document_id)
    assert resp.status_code == 200, resp.text
    conversation_id = resp.json()["conversation_id"]

    # Hội thoại xuất hiện trong list theo document, title = câu hỏi đầu
    resp = client.get(
        "/api/v1/ai/conversations",
        headers={"Authorization": f"Bearer {token}"},
        params={"document_id": document_id},
    )
    assert resp.status_code == 200
    conversations = resp.json()
    assert len(conversations) == 1
    assert conversations[0]["id"] == conversation_id
    assert conversations[0]["title"] == "Sản phẩm tên gì?"

    # 2 tin nhắn đúng vai + đúng thứ tự
    resp = client.get(
        f"/api/v1/ai/conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    messages = resp.json()
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "Sản phẩm tên gì?"),
        ("assistant", "Câu trả lời mẫu"),
    ]


def test_chat_reuses_conversation_for_same_document(
    client, monkeypatch, make_token, db_session_factory
):
    token = _login(client, make_token)
    with db_session_factory() as db:
        user = db.query(User).one()
    document_id = _make_document(db_session_factory, owner_id=user.id)
    _mock_ai_ok(monkeypatch)

    first = _chat(client, token, document_id, question="Câu 1").json()
    second = _chat(client, token, document_id, question="Câu 2").json()

    # Cùng 1 hội thoại, 4 tin nhắn
    assert first["conversation_id"] == second["conversation_id"]
    resp = client.get(
        f"/api/v1/ai/conversations/{first['conversation_id']}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )
    messages = resp.json()
    assert len(messages) == 4
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]


def test_list_conversations_scoped_by_document(
    client, monkeypatch, make_token, db_session_factory
):
    token = _login(client, make_token)
    with db_session_factory() as db:
        user = db.query(User).one()
    doc_a = _make_document(db_session_factory, owner_id=user.id, name="a.pdf")
    doc_b = _make_document(db_session_factory, owner_id=user.id, name="b.pdf")
    _mock_ai_ok(monkeypatch)
    _chat(client, token, doc_a, question="Hỏi về A")
    _chat(client, token, doc_b, question="Hỏi về B")

    resp = client.get(
        "/api/v1/ai/conversations",
        headers={"Authorization": f"Bearer {token}"},
        params={"document_id": doc_a},
    )
    conversations = resp.json()
    assert len(conversations) == 1
    assert conversations[0]["title"] == "Hỏi về A"

    # Không lọc: thấy cả 2 hội thoại của mình
    resp = client.get(
        "/api/v1/ai/conversations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert len(resp.json()) == 2


def test_other_user_cannot_read_or_delete_conversation(
    client, monkeypatch, make_token, db_session_factory
):
    token_a = _login(client, make_token)
    with db_session_factory() as db:
        user = db.query(User).one()
    document_id = _make_document(db_session_factory, owner_id=user.id)
    _mock_ai_ok(monkeypatch)
    conversation_id = _chat(client, token_a, document_id).json()["conversation_id"]

    # User B đăng nhập riêng
    token_b = make_token(sub="g-sub-2", email="other@gmail.com", name="Người B")
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_b}"})
    assert resp.status_code == 200
    headers_b = {"Authorization": f"Bearer {token_b}"}

    resp = client.get(f"/api/v1/ai/conversations/{conversation_id}/messages", headers=headers_b)
    assert resp.status_code == 404

    resp = client.delete(f"/api/v1/ai/conversations/{conversation_id}", headers=headers_b)
    assert resp.status_code == 404

    # User B cũng không thấy hội thoại của A khi list theo document của A
    resp = client.get(
        "/api/v1/ai/conversations",
        headers=headers_b,
        params={"document_id": document_id},
    )
    assert resp.status_code == 404  # document không thuộc B → chặn từ upstream


def test_delete_conversation_removes_messages(
    client, monkeypatch, make_token, db_session_factory
):
    token = _login(client, make_token)
    with db_session_factory() as db:
        user = db.query(User).one()
    document_id = _make_document(db_session_factory, owner_id=user.id)
    _mock_ai_ok(monkeypatch)
    conversation_id = _chat(client, token, document_id).json()["conversation_id"]

    resp = client.delete(
        f"/api/v1/ai/conversations/{conversation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"detail": "Đã xóa hội thoại"}

    with db_session_factory() as db:
        assert db.query(AiConversation).count() == 0
        assert db.query(AiMessage).count() == 0


def test_delete_document_cascades_conversations(
    client, monkeypatch, make_token, db_session_factory
):
    token = _login(client, make_token)
    with db_session_factory() as db:
        user = db.query(User).one()
    document_id = _make_document(db_session_factory, owner_id=user.id)
    _mock_ai_ok(monkeypatch)
    conversation_id = _chat(client, token, document_id).json()["conversation_id"]

    resp = client.delete(
        f"/api/v1/documents/{document_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    with db_session_factory() as db:
        assert db.query(AiConversation).count() == 0
        assert db.query(AiMessage).count() == 0

    # Hội thoại đã biến mất khỏi API
    resp = client.get(
        f"/api/v1/ai/conversations/{conversation_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
