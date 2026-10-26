"""Test ra lệnh bằng giọng nói: endpoint (auth/wiring) + service (parse/validate/history)."""

import pytest

import app.services.ai_service as ai_service
import app.services.voice_command_service as voice_command_service
from app.schemas.voice import (
    VoiceAppContext,
    VoiceCommandResponse,
    VoiceDocument,
    VoiceFolder,
)
from app.services.voice_command_service import VoiceCommandError


def _login(client, make_token):
    token = make_token(sub="g-sub-1", email="user1@gmail.com", name="Nguyễn Văn A")
    # Warm: request đầu tiên qua /auth/me để dependency resolve+commit user local
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    return token


def _body(transcript="vào tab tài liệu", session_id="sess-00000001"):
    return {
        "transcript": transcript,
        "session_id": session_id,
        "context": {
            "current_tab": "documents",
            "folders": [{"id": "f1", "name": "Hợp đồng"}],
            "documents": [
                {"id": "d1", "name": "hop-dong-2024.pdf", "mime_type": "application/pdf"},
                {"id": "d2", "name": "bao-cao.docx", "mime_type": "application/vnd..."},
            ],
        },
    }


# ---------------------------------------------------------------------------
# Endpoint


def test_voice_command_requires_auth(client):
    response = client.post("/api/v1/ai/voice-command", json=_body())
    assert response.status_code == 401


def test_voice_command_returns_decision(client, monkeypatch, make_token):
    token = _login(client, make_token)
    monkeypatch.setattr(
        "app.api.v1.ai.voice_command_service.interpret",
        lambda transcript, context, session_id: VoiceCommandResponse(
            action="navigate_tab", params={"tab": "documents"}, reply="Đã chuyển tab."
        ),
    )
    response = client.post(
        "/api/v1/ai/voice-command",
        headers={"Authorization": f"Bearer {token}"},
        json=_body(),
    )
    assert response.status_code == 200
    assert response.json() == {
        "action": "navigate_tab",
        "params": {"tab": "documents"},
        "reply": "Đã chuyển tab.",
    }


def test_voice_command_maps_infra_error_to_503(client, monkeypatch, make_token):
    token = _login(client, make_token)
    monkeypatch.setattr(
        "app.api.v1.ai.voice_command_service.interpret",
        lambda transcript, context, session_id: (_ for _ in ()).throw(
            VoiceCommandError("AI chưa được cấu hình ANTHROPIC_AUTH_TOKEN trên backend")
        ),
    )
    response = client.post(
        "/api/v1/ai/voice-command",
        headers={"Authorization": f"Bearer {token}"},
        json=_body(),
    )
    assert response.status_code == 503
    assert "ANTHROPIC_AUTH_TOKEN" in response.json()["detail"]


def test_voice_command_rejects_empty_transcript(client, monkeypatch, make_token):
    token = _login(client, make_token)
    response = client.post(
        "/api/v1/ai/voice-command",
        headers={"Authorization": f"Bearer {token}"},
        json=_body(transcript=""),
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Service: parse kết quả từ API Anthropic Messages


def _tool_use(name, args=None):
    return {"content": [{"type": "tool_use", "name": name, "input": args or {}}]}


def _text_reply(text):
    return {"content": [{"type": "text", "text": text}]}


def test_interpret_returns_action_from_tool_use(monkeypatch):
    captured = {}

    def fake_post(payload):
        captured["payload"] = payload
        return _tool_use("navigate_tab", {"tab": "documents"})

    monkeypatch.setattr(voice_command_service.ai_service, "post_anthropic", fake_post)
    decision = voice_command_service.interpret(
        transcript="vào tab tài liệu",
        context=VoiceAppContext(current_tab="ai"),
        session_id="s1",
    )
    assert decision.action == "navigate_tab"
    assert decision.params == {"tab": "documents"}
    assert decision.reply


def test_interpret_text_reply_gives_no_action(monkeypatch):
    monkeypatch.setattr(
        voice_command_service.ai_service,
        "post_anthropic",
        lambda payload: _text_reply("Bạn muốn mở file nào?"),
    )
    decision = voice_command_service.interpret(
        transcript="mở file",
        context=VoiceAppContext(),
        session_id="s2",
    )
    assert decision.action is None
    assert decision.params == {}
    assert decision.reply == "Bạn muốn mở file nào?"


def test_interpret_rejects_unknown_tool(monkeypatch):
    monkeypatch.setattr(
        voice_command_service.ai_service,
        "post_anthropic",
        lambda payload: _tool_use("open_youtube", {"url": "x"}),
    )
    decision = voice_command_service.interpret(
        transcript="mở youtube",
        context=VoiceAppContext(),
        session_id="s3",
    )
    assert decision.action is None
    assert "hỗ trợ" in decision.reply


def test_interpret_rejects_invalid_enum_value(monkeypatch):
    monkeypatch.setattr(
        voice_command_service.ai_service,
        "post_anthropic",
        lambda payload: _tool_use("navigate_tab", {"tab": "youtube"}),
    )
    decision = voice_command_service.interpret(
        transcript="mở youtube",
        context=VoiceAppContext(),
        session_id="s4",
    )
    assert decision.action is None


def test_interpret_rejects_missing_required_param(monkeypatch):
    monkeypatch.setattr(
        voice_command_service.ai_service,
        "post_anthropic",
        lambda payload: _tool_use("run_ocr", {}),
    )
    decision = voice_command_service.interpret(
        transcript="quét ocr",
        context=VoiceAppContext(),
        session_id="s5",
    )
    assert decision.action is None
    assert decision.reply


def test_interpret_maps_ai_service_error(monkeypatch):
    def boom(payload):
        raise ai_service.AIServiceError("Không kết nối được dịch vụ AI")

    monkeypatch.setattr(voice_command_service.ai_service, "post_anthropic", boom)
    with pytest.raises(VoiceCommandError):
        voice_command_service.interpret(
            transcript="hello",
            context=VoiceAppContext(),
            session_id="s6",
        )


def test_interpret_prompt_contains_names_but_not_ids(monkeypatch):
    captured = {}

    def fake_post(payload):
        captured["payload"] = payload
        return _text_reply("ok")

    monkeypatch.setattr(voice_command_service.ai_service, "post_anthropic", fake_post)
    context = VoiceAppContext(
        current_tab="documents",
        folders=[VoiceFolder(id="f1", name="Hợp đồng")],
        documents=[
            VoiceDocument(
                id="d1", name="hop-dong-2024.pdf", mime_type="application/pdf"
            )
        ],
    )
    voice_command_service.interpret(transcript="mở file hợp đồng", context=context, session_id="s7")
    prompt = captured["payload"]["messages"][-1]["content"]
    assert "hop-dong-2024.pdf" in prompt
    assert "d1" not in prompt


# ---------------------------------------------------------------------------
# Service: lịch sử hội thoại


def test_history_is_sent_and_capped(monkeypatch):
    captured = {}

    def fake_post(payload):
        captured["payload"] = payload
        return _text_reply("ok")

    monkeypatch.setattr(voice_command_service.ai_service, "post_anthropic", fake_post)
    for i in range(12):
        voice_command_service.interpret(
            transcript=f"lệnh số {i}",
            context=VoiceAppContext(),
            session_id="hist",
        )
    messages = captured["payload"]["messages"]
    user_turns = [c for c in messages if c["role"] == "user"]
    assert any("lệnh số 11" in c["content"] for c in user_turns)
    assert all("lệnh số 0\n" not in c["content"] + "\n" for c in user_turns)
    # +1 vì lượt hiện tại nằm ngoài history đã trim
    assert len(user_turns) <= voice_command_service.MAX_HISTORY_TURNS + 1


def test_history_is_isolated_between_sessions(monkeypatch):
    captured = {}

    def fake_post(payload):
        captured["payload"] = payload
        return _text_reply("ok")

    monkeypatch.setattr(voice_command_service.ai_service, "post_anthropic", fake_post)
    voice_command_service.interpret(
        transcript="của session A", context=VoiceAppContext(), session_id="a"
    )
    voice_command_service.interpret(
        transcript="của session B", context=VoiceAppContext(), session_id="b"
    )
    texts = [c["content"] for c in captured["payload"]["messages"]]
    assert not any("session A" in t for t in texts)
