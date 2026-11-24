"""Chọn action từ lệnh giọng nói bằng tool use của API Anthropic Messages (REST thuần).

Nguyên tắc:
- Backend KHÔNG thực thi action — chỉ trả về tên action + tham số là TÊN
  (tài liệu/thư mục). Client tự resolve tên → id trong danh sách nó gửi lên,
  nên AI không bao giờ cần (hay bịa được) id.
- Chỉ chấp nhận action nằm trong whitelist `_ACTIONS`; tham số được validate
  kiểu/enum trước khi trả client. Action không hợp lệ → trả action=None kèm
  reply giải thích (client hiển thị, không thực thi gì).
"""

from app.core.config import get_settings
from app.schemas.voice import VoiceAppContext, VoiceCommandResponse, VoiceDocument
from app.services import ai_service

# Số lượt (user+model) giữ lại cho mỗi phiên voice — đủ hiểu "file lúc nãy"
# mà không gửi dữ liệu thừa lên API.
MAX_HISTORY_TURNS = 10

_TABS = ("dashboard", "documents", "ai", "account")
_TAB_LABELS = {
    "dashboard": "Overview",
    "documents": "Documents",
    "ai": "AI",
    "account": "Account",
}
_AI_TOOLS = ("ocr", "chat", "translate")
_AI_TOOL_LABELS = {"ocr": "OCR", "chat": "Chat with AI", "translate": "Translate text"}
_READ_TARGETS = ("ocr_result", "chat_answer", "translation", "reply")

# Registry action: nguồn duy nhất cho (1) khai báo tool gửi AI và
# (2) validate tham số trả về. Kiểu tham số: "string" | "array".
_ACTIONS: dict[str, dict[str, object]] = {
    "navigate_tab": {
        "description": "Switch to one of the app tabs.",
        "params": {"tab": {"type": "string", "enum": list(_TABS)}},
        "required": ("tab",),
        "reply": "Switched to the {tab} tab.",
    },
    "open_ai_tool": {
        "description": "Open one of the tools in the AI tab.",
        "params": {"tool": {"type": "string", "enum": list(_AI_TOOLS)}},
        "required": ("tool",),
        "reply": "Opened the {tool} tool.",
    },
    "select_folder": {
        "description": "Filter the document list by folder.",
        "params": {"folder_name": {"type": "string"}},
        "required": ("folder_name",),
        "reply": "Filtered documents by the {folder_name} folder.",
    },
    "list_documents": {
        "description": "List the available documents (all, or inside one folder).",
        "params": {"folder_name": {"type": "string"}},
        "required": (),
        "reply": "Listing documents.",
    },
    "open_document": {
        "description": "Open a document in the PDF viewer.",
        "params": {"name_query": {"type": "string"}},
        "required": ("name_query",),
        "reply": "Opening {name_query}.",
    },
    "run_ocr": {
        "description": "Run OCR to extract text from a document.",
        "params": {"name_query": {"type": "string"}},
        "required": ("name_query",),
        "reply": "Running OCR on {name_query}.",
    },
    "ask_chat": {
        "description": "Ask the AI a question about a document (chat with the document).",
        "params": {"question": {"type": "string"}, "name_query": {"type": "string"}},
        "required": ("question",),
        "reply": "Looking up the answer.",
    },
    "translate_text": {
        "description": "Translate a piece of text.",
        "params": {"text": {"type": "string"}, "target_language": {"type": "string"}},
        "required": ("text",),
        "reply": "Translating the text.",
    },
    "read_aloud": {
        "description": "Read the currently shown content out loud.",
        "params": {"what": {"type": "string", "enum": list(_READ_TARGETS)}},
        "required": (),
        "reply": "Reading the content out loud.",
    },
    "stop_speaking": {
        "description": "Stop the current read-aloud playback.",
        "params": {},
        "required": (),
        "reply": "Stopped reading.",
    },
    "delete_document": {
        "description": (
            "Delete a document — the app shows a confirmation dialog, "
            "nothing is deleted immediately."
        ),
        "params": {"name_query": {"type": "string"}},
        "required": ("name_query",),
        "reply": "Waiting for confirmation to delete {name_query}.",
    },
    "merge_documents": {
        "description": (
            "Merge several PDFs — the app shows a naming dialog so the user can review."
        ),
        "params": {
            "names": {"type": "array"},
            "new_name": {"type": "string"},
        },
        "required": (),
        "reply": "Waiting for confirmation to merge the documents.",
    },
    "split_document": {
        "description": (
            "Split a PDF by page ranges — the app shows a dialog to review the ranges."
        ),
        "params": {"name_query": {"type": "string"}, "ranges": {"type": "string"}},
        "required": ("name_query",),
        "reply": "Waiting for the page ranges to split.",
    },
}

# Lịch sử hội thoại in-memory theo session_id; restart backend là mất (không lưu DB v1).
_HISTORY: dict[str, list[dict[str, object]]] = {}

_SYSTEM_PROMPT = (
    "You are the English-speaking voice assistant of DocuVault (document management + AI). "
    "Your job: understand the user's spoken command and choose EXACTLY ONE tool from the "
    "tool list. "
    "Users speak English and may be brief, use synonyms or be imprecise — reason about it. "
    "If the command is ambiguous or a required parameter is missing, do NOT call a tool and do not "
    "invent parameters: ask a short follow-up question in English. "
    "Document/folder parameters are always NAMES (exactly as listed in the context), never ids. "
    "Only call tools for operations on documents, folders, OCR, translation and AI chat of this "
    "app. "
    "Always answer in English."
)


class VoiceCommandError(Exception):
    """Không gọi được dịch vụ AI để phân tích lệnh."""


def _tools() -> list[dict[str, object]]:
    """Khai báo tool theo schema Anthropic Messages (JSON Schema thường)."""
    tools: list[dict[str, object]] = []
    for name, spec in _ACTIONS.items():
        params = spec["params"]
        assert isinstance(params, dict)
        properties: dict[str, object] = {}
        for param_name, param_spec in params.items():
            assert isinstance(param_spec, dict)
            prop: dict[str, object] = {"type": param_spec["type"]}
            if param_spec["type"] == "array":
                prop["items"] = {"type": "string"}
            if "enum" in param_spec:
                prop["enum"] = param_spec["enum"]
            if param_name in spec["required"]:  # type: ignore[operator]
                prop["description"] = "Required."
            properties[param_name] = prop
        tools.append(
            {
                "name": name,
                "description": spec["description"],
                "input_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": list(spec["required"]),  # type: ignore[arg-type]
                },
            }
        )
    return tools


def _describe_documents(documents: list[VoiceDocument]) -> str:
    if not documents:
        return "(no documents yet)"
    return "\n".join(f"- {d.name} ({d.mime_type or 'unknown type'})" for d in documents[:80])


def _build_prompt(transcript: str, context: VoiceAppContext) -> str:
    folder_names = ", ".join(f.name for f in context.folders) or "(no folders yet)"
    current = context.current_tab or "unknown"
    lines = [
        "DocuVault app context:",
        f"- Current tab: {_TAB_LABELS.get(current, current)}",
        f"- Folders: {folder_names}",
        "- Documents:",
        _describe_documents(context.documents),
        "",
        "The user said:",
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
                return None, f"Command is missing a required parameter ({name})"
            continue
        expected = param_spec["type"]
        if expected == "string" and not isinstance(value, str):
            return None, f"Parameter {name} must be a string"
        if expected == "array":
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                return None, f"Parameter {name} must be a list of names"
        if "enum" in param_spec and value not in param_spec["enum"]:
            return None, f"Invalid value for {name}"
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
    history.append({"role": "user", "content": transcript})
    history.append({"role": "assistant", "content": reply})
    del history[: max(0, len(history) - MAX_HISTORY_TURNS * 2)]


def interpret(transcript: str, context: VoiceAppContext, session_id: str) -> VoiceCommandResponse:
    """Gửi lệnh nói tới AI, trả về action đã validate + câu trả lời."""
    payload: dict[str, object] = {
        "model": get_settings().anthropic_model,
        "max_tokens": 2048,
        "system": _SYSTEM_PROMPT,
        "tools": _tools(),
        "messages": [
            *_HISTORY.get(session_id, []),
            {"role": "user", "content": _build_prompt(transcript, context)},
        ],
    }
    try:
        response = ai_service.post_anthropic(payload)
    except ai_service.AIServiceError as exc:
        raise VoiceCommandError(str(exc)) from exc

    text_reply = ""
    function_call: dict | None = None
    try:
        blocks = response["content"]
    except (KeyError, TypeError) as exc:
        raise VoiceCommandError("The AI service returned no content") from exc
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use" and function_call is None:
            function_call = {"name": block.get("name"), "args": block.get("input") or {}}
        elif block.get("type") == "text" and not text_reply:
            text_reply = str(block["text"])
    if not text_reply and function_call is None:
        raise VoiceCommandError("The AI service returned no content")

    if function_call is None:
        _remember(session_id, transcript, text_reply)
        fallback = "Sorry, I didn't understand that command."
        return VoiceCommandResponse(action=None, params={}, reply=text_reply.strip() or fallback)

    name = str(function_call.get("name", ""))
    args = function_call.get("args") or {}
    if not isinstance(args, dict):
        args = {}
    if name not in _ACTIONS:
        reply = "That feature is not supported by voice yet."
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
