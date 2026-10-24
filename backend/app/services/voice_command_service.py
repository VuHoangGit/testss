"""Chọn action từ lệnh giọng nói bằng Gemini function calling (REST thuần).

Nguyên tắc:
- Backend KHÔNG thực thi action — chỉ trả về tên action + tham số là TÊN
  (tài liệu/thư mục). Client tự resolve tên → id trong danh sách nó gửi lên,
  nên Gemini không bao giờ cần (hay bịa được) id.
- Chỉ chấp nhận action nằm trong whitelist `_ACTIONS`; tham số được validate
  kiểu/enum trước khi trả client. Action không hợp lệ → trả action=None kèm
  reply giải thích (client hiển thị, không thực thi gì).
"""

from app.schemas.voice import VoiceAppContext, VoiceCommandResponse, VoiceDocument
from app.services import ai_service

# Số lượt (user+model) giữ lại cho mỗi phiên voice — đủ hiểu "file lúc nãy"
# mà không gửi dữ liệu thừa lên API.
MAX_HISTORY_TURNS = 10

_TABS = ("dashboard", "documents", "ai", "account")
_TAB_LABELS = {
    "dashboard": "Tổng quan",
    "documents": "Tài liệu",
    "ai": "AI",
    "account": "Tài khoản",
}
_AI_TOOLS = ("ocr", "chat", "translate")
_AI_TOOL_LABELS = {"ocr": "OCR", "chat": "Chat với AI", "translate": "Dịch văn bản"}
_READ_TARGETS = ("ocr_result", "chat_answer", "translation", "reply")

# Registry action: nguồn duy nhất cho (1) khai báo tool gửi Gemini và
# (2) validate tham số trả về. Kiểu tham số: "string" | "array".
_ACTIONS: dict[str, dict[str, object]] = {
    "navigate_tab": {
        "description": "Chuyển sang tab của ứng dụng.",
        "params": {"tab": {"type": "string", "enum": list(_TABS)}},
        "required": ("tab",),
        "reply": "Đã chuyển đến tab {tab}.",
    },
    "open_ai_tool": {
        "description": "Mở một công cụ trong tab AI.",
        "params": {"tool": {"type": "string", "enum": list(_AI_TOOLS)}},
        "required": ("tool",),
        "reply": "Đã mở công cụ {tool}.",
    },
    "select_folder": {
        "description": "Lọc danh sách tài liệu theo thư mục.",
        "params": {"folder_name": {"type": "string"}},
        "required": ("folder_name",),
        "reply": "Đã lọc theo thư mục {folder_name}.",
    },
    "list_documents": {
        "description": "Liệt kê tài liệu hiện có (toàn bộ hoặc trong một thư mục).",
        "params": {"folder_name": {"type": "string"}},
        "required": (),
        "reply": "Đang liệt kê tài liệu.",
    },
    "open_document": {
        "description": "Mở một tài liệu trong trình xem PDF.",
        "params": {"name_query": {"type": "string"}},
        "required": ("name_query",),
        "reply": "Đang mở tài liệu {name_query}.",
    },
    "run_ocr": {
        "description": "Chạy OCR trích xuất văn bản cho một tài liệu.",
        "params": {"name_query": {"type": "string"}},
        "required": ("name_query",),
        "reply": "Đang quét OCR tài liệu {name_query}.",
    },
    "ask_chat": {
        "description": "Hỏi đáp AI về một tài liệu (chat với tài liệu).",
        "params": {"question": {"type": "string"}, "name_query": {"type": "string"}},
        "required": ("question",),
        "reply": "Đang tìm câu trả lời.",
    },
    "translate_text": {
        "description": "Dịch một đoạn văn bản.",
        "params": {"text": {"type": "string"}, "target_language": {"type": "string"}},
        "required": ("text",),
        "reply": "Đang dịch đoạn văn.",
    },
    "read_aloud": {
        "description": "Đọc to nội dung đang hiển thị.",
        "params": {"what": {"type": "string", "enum": list(_READ_TARGETS)}},
        "required": (),
        "reply": "Đang đọc nội dung.",
    },
    "stop_speaking": {
        "description": "Dừng việc đọc to đang phát.",
        "params": {},
        "required": (),
        "reply": "Đã dừng đọc.",
    },
    "delete_document": {
        "description": "Xóa một tài liệu — ứng dụng sẽ hiện hộp thoại xác nhận, không xóa ngay.",
        "params": {"name_query": {"type": "string"}},
        "required": ("name_query",),
        "reply": "Chờ xác nhận xóa tài liệu {name_query}.",
    },
    "merge_documents": {
        "description": "Gộp nhiều PDF — ứng dụng sẽ hiện hộp thoại đặt tên để duyệt lại.",
        "params": {
            "names": {"type": "array"},
            "new_name": {"type": "string"},
        },
        "required": (),
        "reply": "Chờ xác nhận gộp tài liệu.",
    },
    "split_document": {
        "description": (
            "Tách PDF theo khoảng trang — ứng dụng sẽ hiện hộp thoại nhập lại khoảng trang."
        ),
        "params": {"name_query": {"type": "string"}, "ranges": {"type": "string"}},
        "required": ("name_query",),
        "reply": "Chờ nhập khoảng trang để tách.",
    },
}

# Lịch sử hội thoại in-memory theo session_id; restart backend là mất (không lưu DB v1).
_HISTORY: dict[str, list[dict[str, object]]] = {}

_SYSTEM_PROMPT = (
    "Bạn là trợ lý giọng nói tiếng Việt của ứng dụng DocuVault (quản lý tài liệu + AI). "
    "Nhiệm vụ: hiểu lệnh nói của người dùng và chọn ĐÚNG MỘT công cụ trong danh sách công cụ. "
    "Người dùng có thể nói ngắn gọn, dùng từ đồng nghĩa hoặc không chính xác — hãy suy luận. "
    "Nếu lệnh mơ hồ hoặc thiếu tham số bắt buộc, KHÔNG gọi công cụ và không bịa tham số: "
    "hãy hỏi lại ngắn gọn bằng tiếng Việt. "
    "Tham số tài liệu/thư mục luôn là TÊN (đúng như danh sách trong ngữ cảnh), không phải id. "
    "Chỉ gọi công cụ cho các thao tác liên quan tài liệu, thư mục, OCR, dịch, chat AI của ứng dụng."
)


class VoiceCommandError(Exception):
    """Không gọi được dịch vụ AI để phân tích lệnh."""


def _gemini_type(py_type: str) -> str:
    return {"string": "STRING", "array": "ARRAY"}.get(py_type, "STRING")


def _declarations() -> list[dict[str, object]]:
    declarations: list[dict[str, object]] = []
    for name, spec in _ACTIONS.items():
        params = spec["params"]
        assert isinstance(params, dict)
        properties: dict[str, object] = {}
        for param_name, param_spec in params.items():
            assert isinstance(param_spec, dict)
            prop: dict[str, object] = {"type": _gemini_type(param_spec["type"])}
            if "enum" in param_spec:
                prop["enum"] = param_spec["enum"]
            if param_name in spec["required"]:  # type: ignore[operator]
                prop["description"] = "Bắt buộc."
            properties[param_name] = prop
        declarations.append(
            {
                "name": name,
                "description": spec["description"],
                "parameters": {
                    "type": "OBJECT",
                    "properties": properties,
                    "required": list(spec["required"]),  # type: ignore[arg-type]
                },
            }
        )
    return declarations


def _describe_documents(documents: list[VoiceDocument]) -> str:
    if not documents:
        return "(chưa có tài liệu nào)"
    return "\n".join(
        f"- {d.name} ({d.mime_type or 'không rõ loại'})" for d in documents[:80]
    )


def _build_prompt(transcript: str, context: VoiceAppContext) -> str:
    folder_names = ", ".join(f.name for f in context.folders) or "(chưa có thư mục nào)"
    current = context.current_tab or "không rõ"
    lines = [
        "Ngữ cảnh ứng dụng DocuVault:",
        f"- Tab hiện tại: {_TAB_LABELS.get(current, current)}",
        f"- Danh sách thư mục: {folder_names}",
        "- Danh sách tài liệu:",
        _describe_documents(context.documents),
        "",
        "Người dùng nói:",
        transcript,
    ]
    return "\n".join(lines)


def _validate(action: str, args: dict) -> tuple[dict | None, str | None]:
    """Kiểm tra action + tham số. Trả (params_sạch, thông_báo_lỗi)."""
    spec = _ACTIONS[action]
    params_spec = spec["params"]
    assert isinstance(params_spec, dict)
    required = spec["required"]
    assert isinstance(required, tuple)
    clean: dict = {}
    for name, param_spec in params_spec.items():
        assert isinstance(param_spec, dict)
        value = args.get(name)
        if value is None or value == "":
            if name in required:
                return None, f"Lệnh thiếu thông tin bắt buộc ({name})"
            continue
        expected = param_spec["type"]
        if expected == "string" and not isinstance(value, str):
            return None, f"Tham số {name} phải là chuỗi"
        if expected == "array":
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                return None, f"Tham số {name} phải là danh sách tên"
        if "enum" in param_spec and value not in param_spec["enum"]:
            return None, f"Giá trị {name} không hợp lệ"
        clean[name] = value
    return clean, None


def _format_reply(action: str, params: dict) -> str:
    template = _ACTIONS[action]["reply"]
    assert isinstance(template, str)
    labels = {"tab": _TAB_LABELS, "tool": _AI_TOOL_LABELS}
    formatted = dict(params)
    for key, mapping in labels.items():
        if key in formatted:
            formatted[key] = mapping.get(str(formatted[key]), str(formatted[key]))
    try:
        return template.format(**formatted)
    except (KeyError, IndexError):
        return template


def _remember(session_id: str, transcript: str, reply: str) -> None:
    history = _HISTORY.setdefault(session_id, [])
    history.append({"role": "user", "parts": [{"text": transcript}]})
    history.append({"role": "model", "parts": [{"text": reply}]})
    del history[: max(0, len(history) - MAX_HISTORY_TURNS * 2)]


def interpret(transcript: str, context: VoiceAppContext, session_id: str) -> VoiceCommandResponse:
    """Gửi lệnh nói tới Gemini, trả về action đã validate + câu trả lời."""
    payload: dict[str, object] = {
        "systemInstruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
        "tools": [{"function_declarations": _declarations()}],
        "contents": [
            *_HISTORY.get(session_id, []),
            {"role": "user", "parts": [{"text": _build_prompt(transcript, context)}]},
        ],
    }
    try:
        response = ai_service.post_gemini(payload)
    except ai_service.AIServiceError as exc:
        raise VoiceCommandError(str(exc)) from exc

    text_reply = ""
    function_call: dict | None = None
    try:
        parts = response["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError) as exc:
        raise VoiceCommandError("Dịch vụ AI không trả về nội dung") from exc
    for part in parts:
        if not isinstance(part, dict):
            continue
        if "functionCall" in part and function_call is None:
            function_call = part["functionCall"]
        elif "text" in part and not text_reply:
            text_reply = str(part["text"])
    if not text_reply and function_call is None:
        raise VoiceCommandError("Dịch vụ AI không trả về nội dung")

    if function_call is None:
        _remember(session_id, transcript, text_reply)
        fallback = "Xin lỗi, tôi chưa hiểu lệnh này."
        return VoiceCommandResponse(
            action=None, params={}, reply=text_reply.strip() or fallback
        )

    name = str(function_call.get("name", ""))
    args = function_call.get("args") or {}
    if not isinstance(args, dict):
        args = {}
    if name not in _ACTIONS:
        reply = "Tính năng này chưa được hỗ trợ bằng giọng nói."
        _remember(session_id, transcript, reply)
        return VoiceCommandResponse(action=None, params={}, reply=reply)
    clean, error = _validate(name, args)
    if clean is None:
        assert error is not None
        _remember(session_id, transcript, error)
        return VoiceCommandResponse(action=None, params={}, reply=error)
    reply = _format_reply(name, clean)
    _remember(session_id, transcript, reply)
    return VoiceCommandResponse(action=name, params=clean, reply=reply)
