"""AI document operations backed by an Anthropic-compatible Messages API.

Chạy qua endpoint tương thích Anthropic (vd GLM của z.ai) — cấu hình trong
.env: ANTHROPIC_AUTH_TOKEN / ANTHROPIC_BASE_URL / ANTHROPIC_MODEL. Token chỉ
đọc từ cấu hình server, không bao giờ nhận từ client hay trả về trong response.
"""

import io
import logging
import re
from dataclasses import dataclass

import requests
from docx import Document as WordDocument
from pypdf import PdfReader

from app.core.config import get_settings
from app.services import docx_service

# Dòng dài hơn mức này hiếm khi là tiêu đề (dễ là đoạn văn bị ngắt dòng) →
# không nâng thành heading dù cỡ chữ to.
_MAX_HEADING_LINE_CHARS = 200

# Dòng tiêu đề do [_lines_to_markdown] sinh ra: "# " / "## " / "### " + chữ.
_MARKER_RE = re.compile(r"^(#{1,6}) \S")

# Dòng phải đứng riêng, không gom vào đoạn văn: gạch đầu dòng, mục đánh số,
# hàng bảng, dòng trích dẫn.
_STANDALONE_RE = re.compile(r"^(?:[-*+•–—]\s|\d{1,3}[.)]\s|\||>)")

# Dòng chỉ có ký hiệu gạch đầu dòng (PDF vẽ dấu bằng lượt chữ riêng).
_BULLET_ONLY_RE = re.compile(r"[•·▪◦‣∙]+")

# Khoảng cách dòng lớn hơn bội số này so với nhịp dòng thường → hết đoạn.
_PARAGRAPH_GAP_RATIO = 1.35

# Khe hở giữa hai ký tự (theo bội số cỡ chữ) đủ lớn để coi là thiếu một dấu
# cách. Đo trên Proposal.pdf (cỡ 12) với hộp bao rộng của pdfium (hộp tiến
# glyph, không phải hộp mực): khe hở trong cùng một từ ≤ 0.041, chỗ pdfium bỏ
# mất dấu cách là 0.147–0.149 → ngưỡng 0.09 nằm giữa hai mức, cách đều cả hai.
_WORD_GAP_RATIO = 0.09


@dataclass(frozen=True)
class _PdfLine:
    """Một dòng chữ trên trang PDF: nội dung, cỡ chữ và toạ độ (điểm PDF).

    Toạ độ dùng để biết dòng nào là phần tiếp theo của cùng một đoạn văn (dòng
    trước chạm mép phải của cột → chữ tự xuống dòng) và dòng nào mở đoạn mới.
    """

    text: str
    size: float
    left: float
    right: float
    top: float


class AIServiceError(Exception):
    """A configured AI operation could not be completed."""


# Ghi log nguyên nhân thật (timeout/DNS/5xx gateway) — câu lỗi trả client có
# thể bị rút gọn nhưng log phải đủ để chẩn đoán không cần tái hiện lỗi.
logger = logging.getLogger(__name__)


def _messages_url(base_url: str) -> str:
    """URL endpoint /v1/messages, tránh lặp `/v1` khi base_url đã có sẵn đuôi đó.

    Anthropic gốc: base `https://api.anthropic.com` → nối `/v1/messages`.
    Endpoint tương thích của Google (`…/apps/anthropic-api/v1`) đã kết thúc
    bằng `/v1` → chỉ nối `/messages`, kẻo ra `/v1/v1/messages` (404).
    """
    base = base_url.rstrip("/")
    suffix = "/messages" if base.endswith("/v1") else "/v1/messages"
    return f"{base}{suffix}"


def _auth_headers(settings) -> dict[str, str]:
    """Header xác thực theo nhà cung cấp.

    Google (token dạng `AQ.`) chỉ nhận `x-api-key` — gửi thêm
    `Authorization: Bearer` bằng API key sẽ bị từ chối 401 (Google chỉ chấp
    nhận Bearer với OAuth token). Gateway litellm/new-api (vd dev-gw.vtvlive.vn)
    thì đọc Bearer, nên gửi cả hai như trước.
    """
    if settings.anthropic_auth_token.startswith("AQ."):
        return {
            "x-api-key": settings.anthropic_auth_token,
            "anthropic-version": "2023-06-01",
        }
    return {
        "x-api-key": settings.anthropic_auth_token,
        "Authorization": f"Bearer {settings.anthropic_auth_token}",
        "anthropic-version": "2023-06-01",
    }


def _is_google_settings(settings) -> bool:
    """True khi cấu hình trỏ sang Google (Gemini API) thay vì Anthropic/gateway.

    Nhận biết theo tiền tố `AQ.` của key AI Studio — endpoint tương thích
    Anthropic của Google không cấp cho key loại này, nên phải gọi API gốc
    `generateContent` (xem [_post_google]).
    """
    return settings.anthropic_auth_token.startswith("AQ.")


def _google_model_name(model: str) -> str:
    """Tên model Gemini dùng cho URL `models/{model}:generateContent`.

    Model lỗi thời được đổi sang model flash đã xác nhận hoạt động cho key
    AI Studio (AQ.*). Nếu .env đã đặt tên `gemini-*` thì giữ nguyên để người
    dùng tự chọn phiên bản.
    """
    lowered = model.lower()
    if lowered.startswith("gemini-"):
        return model
    return "gemini-3-flash-preview"


def _tools_for_gemini(tools: object) -> list[dict[str, object]]:
    """Dịch khai báo tools Anthropic (voice command) → functionDeclarations.

    Anthropic: `{"name", "description", "input_schema"}`; Gemini muốn
    `parameters` thay cho `input_schema` — các trường còn lại giữ nguyên.
    """
    declarations: list[dict[str, object]] = []
    for tool in tools or []:  # type: ignore[union-attr]
        if not isinstance(tool, dict):
            continue
        input_schema = tool.get("input_schema")
        parameters = (
            dict(input_schema)
            if isinstance(input_schema, dict)
            else {"type": "object", "properties": {}}
        )
        properties = parameters.get("properties")
        if isinstance(properties, dict):
            normalized_properties: dict[str, object] = {}
            for name, schema in properties.items():
                if not isinstance(schema, dict):
                    normalized_properties[name] = schema
                    continue
                normalized = dict(schema)
                if normalized.get("type") == "array" and "items" not in normalized:
                    normalized["items"] = {"type": "string"}
                normalized_properties[name] = normalized
            parameters["properties"] = normalized_properties
        declarations.append({
            "name": tool.get("name"),
            "description": tool.get("description"),
            "parameters": parameters or {"type": "object"},
        })
    return declarations


def _to_google_payload(payload: dict[str, object]) -> dict[str, object]:
    """Dịch payload Anthropic Messages → Gemini generateContent.

    Chỉ dịch những gì DocuVault gửi: system, messages (text + image base64),
    tools (function declarations cho voice command), max_tokens, temperature.
    `temperature=0` (OCR cần chính xác) tắt luôn thinking của Gemini để trả
    lời nhanh — suy luận không giúp chép tài liệu đúng từng con số.
    """
    system = payload.get("system")
    contents: list[dict[str, object]] = []
    for message in payload.get("messages") or []:
        role = "model" if message.get("role") == "assistant" else "user"
        content = message.get("content")
        parts: list[dict[str, object]] = []
        if isinstance(content, str):
            parts.append({"text": content})
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    parts.append({"text": str(block.get("text") or "")})
                elif block.get("type") == "image":
                    source = block.get("source") or {}
                    parts.append({
                        "inlineData": {
                            "mimeType": source.get("media_type"),
                            "data": source.get("data"),
                        }
                    })
        contents.append({"role": role, "parts": parts})
    body: dict[str, object] = {"contents": contents}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    config: dict[str, object] = {}
    if payload.get("max_tokens") is not None:
        config["maxOutputTokens"] = payload["max_tokens"]
    if payload.get("temperature") is not None:
        config["temperature"] = payload["temperature"]
        if payload["temperature"] == 0:
            config["thinkingConfig"] = {"thinkingBudget": 0}
    if "thinkingConfig" not in config:
        # Gemini 3 có thể dùng hết output budget cho phần suy luận. Tắt
        # thinking mặc định để các chức năng text/voice luôn nhận câu trả lời.
        config["thinkingConfig"] = {"thinkingBudget": 0}
    tools = payload.get("tools")
    if tools:
        declarations = _tools_for_gemini(tools)
        if declarations:
            body["tools"] = [{"functionDeclarations": declarations}]
    if config:
        body["generationConfig"] = config
    return body


def _to_anthropic_response(google_response: dict[str, object]) -> dict[str, object]:
    """Dịch phản hồi Gemini generateContent → dạng content blocks của Anthropic.

    Dùng chung cho mọi service (chat/translate/OCR đọc block "text") và voice
    command (đọc block "tool_use" dựng từ functionCall của Gemini).
    """
    candidates = google_response.get("candidates") or []
    content: list[dict[str, object]] = []
    if candidates and isinstance(candidates[0], dict):
        for part in candidates[0].get("content", {}).get("parts", []):
            if not isinstance(part, dict):
                continue
            if part.get("text"):
                content.append({"type": "text", "text": part.get("text")})
            call = part.get("functionCall")
            if isinstance(call, dict):
                content.append({
                    "type": "tool_use",
                    "name": call.get("name"),
                    "input": call.get("args") or {},
                })
    return {"content": content}


def _failed_host(exc: requests.ConnectionError) -> str | None:
    """Rút tên máy chủ thật sự kết nối fail, từ văn bản exception của requests.

    requests nhúng địa chỉ dưới dạng `host='dev-gw.vtvlive.vn'` (hoặc
    `host=...` trong SSLError/ProxyError). Trả None khi không tìm thấy để nơi
    gọi lùi về ANTHROPIC_BASE_URL.
    """
    match = re.search(r"host='([^']+)'", str(exc))
    return match.group(1) if match else None


def _post_google(payload: dict[str, object], settings) -> dict[str, object]:
    """Gọi Gemini generateContent với payload đã dịch, trả JSON kiểu Anthropic.

    URL gốc `https://generativelanguage.googleapis.com/v1beta/models/…` cố
    định — `.env` chỉ cần đổi key; `ANTHROPIC_BASE_URL` vẫn giữ vai trò cho
    gateway Anthropic/litellm khi quay lại cấu hình cũ.
    """
    model = _google_model_name(str(payload.get("model") or settings.anthropic_model))
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    response = requests.post(
        url,
        headers={
            "x-goog-api-key": settings.anthropic_auth_token,
            "content-type": "application/json",
        },
        json=_to_google_payload(payload),
        timeout=settings.anthropic_timeout_seconds,
    )
    response.raise_for_status()
    return _to_anthropic_response(response.json())


def post_anthropic(payload: dict[str, object]) -> dict[str, object]:
    """POST payload tuỳ ý tới dịch vụ AI (Anthropic Messages hoặc Gemini),
    trả JSON dạng content blocks như Anthropic.

    Dùng chung cho các tác vụ chỉ cần text (qua request_anthropic) và tác vụ
    cần tool use (voice command) — cùng một chỗ xử lý lỗi/timeout.
    """
    settings = get_settings()
    if not settings.anthropic_auth_token:
        raise AIServiceError("AI is not configured: ANTHROPIC_AUTH_TOKEN is missing on the backend")
    try:
        if _is_google_settings(settings):
            return _post_google(payload, settings)
        response = requests.post(
            _messages_url(settings.anthropic_base_url),
            headers=_auth_headers(settings),
            json=payload,
            timeout=settings.anthropic_timeout_seconds,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        status = getattr(exc.response, "status_code", None)
        detail = _error_message(exc.response)
        model = str(payload.get("model") or settings.anthropic_model)
        # Ghi log nguyên nhân thật trước khi dịch sang câu lỗi thân thiện.
        logger.warning(
            "AI gateway %s failed for model %s: %s %s",
            settings.anthropic_base_url,
            model,
            type(exc).__name__,
            str(exc)[:500],
        )
        # Timeout kết nối/phản hồi: gateway chậm hoặc tắc — câu riêng để không
        # nhầm với "mất kết nối" (DNS/mạng đứt).
        if isinstance(exc, requests.ConnectTimeout):
            raise AIServiceError(
                "The AI service did not accept the connection in time "
                f"({settings.anthropic_timeout_seconds}s) — the gateway may be "
                "overloaded"
            ) from exc
        if isinstance(exc, requests.ReadTimeout):
            raise AIServiceError(
                "The AI service took too long to answer "
                f"(>{settings.anthropic_timeout_seconds}s) — try again"
            ) from exc
        # Không nối được tới gateway: DNS sai/mạng đứt/base_url sai. Nêu địa
        # chỉ thật sự fail (lấy từ exception) — có thể là proxy chứ không
        # phải gateway trong ANTHROPIC_BASE_URL, nói sai sẽ dẫn chẩn đoán lệch.
        if isinstance(exc, requests.ConnectionError):
            failed_host = _failed_host(exc)
            where = failed_host or settings.anthropic_base_url
            raise AIServiceError(
                f"Cannot reach the AI service at {where} "
                "— check the network or ANTHROPIC_BASE_URL"
            ) from exc
        # 403 có thể là key hết hạn, hoặc key KHÔNG được cấp quyền model này
        # (z.ai: "key not allowed to access model … models=['mg::text']").
        if status in (401, 403) and "model" in detail.lower():
            raise AIServiceError(
                f"The AI key is not allowed to use model '{model}' "
                f"({detail}). Use a key with access to that model, or change "
                "ANTHROPIC_MODEL / OCR_VISION_MODEL in .env."
            ) from exc
        if status in (401, 403):
            raise AIServiceError(
                "ANTHROPIC_AUTH_TOKEN is invalid or has been revoked"
            ) from exc
        if status == 404:
            raise AIServiceError(
                f"Model '{settings.anthropic_model}' was not found on the AI service"
            ) from exc
        # 429: gateway rate-limit/quota — thử lại sau, không phải lỗi cấu hình.
        if status == 429:
            raise AIServiceError(
                "The AI service is rate limiting requests, wait a moment and try again"
            ) from exc
        # 5xx: gateway quá tải/lỗi nội bộ — phân biệt với lỗi kết nối.
        if status is not None and status >= 500:
            raise AIServiceError(
                f"The AI service is having problems (HTTP {status}), try again later"
            ) from exc
        # Model text-only nhận block ảnh → từ chối ngay (GLM: "content.type is
        # invalid, allowed values: ['text']").
        if status == 400 and "image" not in detail.lower() and (
            "content.type is invalid" in detail or "allowed values: ['text']" in detail
        ):
            raise AIServiceError(
                f"Model '{model}' cannot read images (text only), so scanned "
                "pages cannot be OCR'd. Set OCR_VISION_MODEL in .env to a "
                "vision-capable model."
            ) from exc
        raise AIServiceError("Could not connect to the AI service") from exc
    except ValueError as exc:
        raise AIServiceError("The AI service returned invalid data") from exc


def _error_message(response: object) -> str:
    """Lấy `error.message` trong body lỗi của dịch vụ AI ('' nếu không có)."""
    try:
        body = response.json()  # type: ignore[attr-defined]
    except (ValueError, AttributeError):
        return ""
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str):
                return message
    return ""


def request_anthropic(
    content: list[dict[str, object]],
    *,
    system: str | None = None,
    temperature: float | None = None,
    max_tokens: int = 8192,
    model: str | None = None,
) -> str:
    """Gửi 1 lượt user (content blocks) và lấy block text đầu tiên.

    Bỏ qua block "thinking" — model GLM trả kèm block suy luận trước câu trả lời.
    `system` = luật chung (OCR dùng để đặt bộ luật chép tài liệu);
    `temperature=0` = tắt "sáng tạo" cho tác vụ cần chính xác từng con số;
    `model` = ghi đè model cho riêng lượt này (OCR ảnh cần model vision).
    """
    settings = get_settings()
    payload: dict[str, object] = {
        "model": model or settings.anthropic_model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }
    if system:
        payload["system"] = system
    if temperature is not None:
        payload["temperature"] = temperature
    response = post_anthropic(payload)
    try:
        for block in response["content"]:
            if isinstance(block, dict) and block.get("type") == "text":
                return str(block["text"])
    except (KeyError, TypeError) as exc:
        raise AIServiceError("The AI service returned no content") from exc
    raise AIServiceError("The AI service returned no content")


def extract_pdf_pages(data: bytes) -> list[str]:
    """Văn bản lớp text của từng trang PDF (giữ chỉ số trang) — "" nếu trang scan.

    Giữ riêng từng trang để OCR biết trang nào đã có chữ (khỏi gọi AI) và trang
    nào là ảnh scan cần đọc bằng vision.
    """
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise AIServiceError("The PDF is encrypted, remove its password first")
        return [(page.extract_text() or "").strip() for page in reader.pages]
    except AIServiceError:
        raise
    except Exception as exc:
        raise AIServiceError("Could not read the PDF content") from exc


def extract_pdf_text(data: bytes) -> str:
    """Toàn bộ văn bản lớp text của PDF, các trang cách nhau 1 dòng trống."""
    return "\n\n".join(page for page in extract_pdf_pages(data) if page).strip()


def extract_pdf_pages_markdown(data: bytes) -> list[str]:
    """Như [extract_pdf_pages] nhưng giữ cấu trúc: tiêu đề có `#`, đoạn liền mạch.

    Chữ lấy bằng pdfium (engine của Chrome) chứ không phải pypdf: pypdf tự chèn
    dấu cách khi thấy khe hở giữa hai ký tự rộng hơn dấu cách, nên với văn bản
    căn đều hai bên (justify) hoặc có kerning nó chèn vào giữa từ — bản Word
    xuất ra bị "video ch ất lượng", "công đoạ n", "th ời gian".

    Cấu trúc suy từ cỡ chữ và toạ độ dòng (xem [_lines_to_markdown]):
    dòng bị ngắt giữa câu được gom lại thành một đoạn, dòng cỡ lớn thành heading.

    Dùng cho luồng OCR; luồng dịch/tóm tắt vẫn dùng [extract_pdf_pages] để văn
    bản gửi model không bị lẫn dấu Markdown.

    pdfium KHÔNG đọc được PDF có mật khẩu và bỏ ký tự emoji (glyph không có
    unicode) — hai trường hợp đó quay về pypdf như trước.
    """
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise AIServiceError("The PDF is encrypted, remove its password first")
    except AIServiceError:
        raise
    except Exception as exc:
        raise AIServiceError("Could not read the PDF content") from exc

    page_lines = _pdfium_page_lines(data)
    if page_lines is None:  # pdfium lỗi/không có → đường cũ
        page_lines = [_safe_page_lines(page) for page in reader.pages]

    pages: list[str] = []
    for index, lines in enumerate(page_lines):
        if lines:
            # Cỡ chữ thân tính riêng từng trang: có trang được vẽ qua phép
            # biến đổi tỉ lệ nên pdfium báo cỡ chữ 170–440 thay vì 12 (CV thiết
            # kế bằng Canva). Lấy cỡ chuẩn của cả tài liệu thì mọi dòng trang đó
            # thành heading.
            pages.append(_lines_to_markdown(lines, _body_font_size([lines])))
        else:  # PDF lạ (font/toạ độ hỏng): quay về trích chữ thuần
            pages.append((reader.pages[index].extract_text() or "").strip())
    return _normalise_heading_levels(pages)


def _pdfium_page_lines(data: bytes) -> list[list[_PdfLine]] | None:
    """Dòng chữ của từng trang bằng pdfium; None nếu pdfium không dùng được."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return None
    try:
        document = pdfium.PdfDocument(data)
    except Exception:  # noqa: BLE001 — PDF hỏng/mật khẩu: để đường pypdf xử lý
        return None
    try:
        return [_pdfium_lines(document[index]) for index in range(len(document))]
    except Exception:  # noqa: BLE001 — pdfium ném nhiều loại lỗi khác nhau
        return None
    finally:
        document.close()


def _pdfium_lines(page) -> list[_PdfLine]:
    """Tách trang thành các dòng kèm cỡ chữ lớn nhất và hộp bao của dòng.

    Dấu cách dựng lại từ toạ độ ký tự: pdfium bỏ mất dấu cách ở một số chỗ (khi
    dấu cách được đặt bằng dịch con trỏ thay vì vẽ glyph) → "sựphát triển",
    "dựán". Khe hở đo trên **hộp rộng** (`loose=True` — hộp tiến glyph), không
    phải hộp mực: hộp mực cho khe hở 0.05–0.23 ngay giữa các chữ trong cùng một
    từ nên không phân biệt được, còn hộp rộng cho khoảng cách rõ ràng (xem
    [_WORD_GAP_RATIO]).
    """
    textpage = page.get_textpage()
    text = textpage.get_text_range(0, textpage.count_chars())
    lines: list[_PdfLine] = []
    parts: list[str] = []
    size = 0.0
    left = right = top = 0.0
    has_box = False
    previous_right = 0.0

    def flush() -> None:
        nonlocal parts, size, left, right, top, has_box, previous_right
        content = "".join(parts).strip()
        if content:
            lines.append(_PdfLine(content, size, left, right, top))
        parts = []
        size = 0.0
        left = right = top = 0.0
        has_box = False
        previous_right = 0.0

    def append_space() -> None:
        if parts and parts[-1] != " ":
            parts.append(" ")

    for index, char in enumerate(text):
        if char == "\n":  # pdfium ngăn dòng bằng "\r\n"
            flush()
            continue
        if char == "\r":
            continue
        box = textpage.get_charbox(index)
        loose = textpage.get_charbox(index, loose=True) or box
        text_object = textpage.get_textobj(index)
        if text_object is not None:
            size = max(size, float(text_object.get_font_size() or 0))
        if char.isspace():
            append_space()
            previous_right = loose[2] if loose else 0.0
            continue
        if loose and previous_right and size > 0:
            if (loose[0] - previous_right) / size >= _WORD_GAP_RATIO:
                append_space()
        # U+FFFE: glyph không có bảng unicode — PDF dùng nó cho dấu gạch nối khi
        # ngắt dòng ("Non￾Linear").
        parts.append("-" if char == "￾" else char)
        if loose:
            previous_right = loose[2]
        if box:
            if has_box:
                left = min(left, box[0])
                right = max(right, box[2])
                top = max(top, box[3])
            else:
                left, right, top = box[0], box[2], box[3]
                has_box = True
        elif previous_right:
            previous_right = 0.0
    flush()
    return lines


def _safe_page_lines(page) -> list[_PdfLine]:
    """Dòng chữ một trang theo pypdf (dự phòng); trang lỗi → [] để đi tiếp."""
    try:
        return _page_lines(page)
    except Exception:  # noqa: BLE001 — pypdf ném nhiều loại lỗi khác nhau
        return []


def _page_lines(page) -> list[_PdfLine]:
    """Ghép các mảnh chữ pypdf trả về thành dòng kèm cỡ chữ, đúng thứ tự đọc.

    Đường dự phòng khi không có pdfium; chữ có thể dính dấu cách thừa (xem
    [extract_pdf_pages_markdown]) nên không dùng làm đường chính.
    """
    lines: list[_PdfLine] = []
    parts: list[str] = []
    size = 0.0

    def flush() -> None:
        nonlocal parts, size
        text = "".join(parts).strip()
        if text:
            # pypdf không trả toạ độ → left/right/top = 0, mọi dòng thành 1 đoạn.
            lines.append(_PdfLine(text, size, 0.0, 0.0, 0.0))
        parts = []
        size = 0.0

    def visitor(text: str, cm, tm, font_dict, font_size) -> None:  # noqa: ARG001
        nonlocal size
        chunks = (text or "").split("\n")
        for position, chunk in enumerate(chunks):
            if chunk:
                parts.append(chunk)
                size = max(size, float(font_size or 0))
            if position < len(chunks) - 1:  # pypdf kết thúc mỗi dòng bằng "\n"
                flush()

    page.extract_text(visitor_text=visitor)
    flush()
    return lines


def _body_font_size(page_lines: list[list[_PdfLine]]) -> float:
    """Cỡ chữ thân văn bản = cỡ chiếm nhiều ký tự nhất trong cả tài liệu."""
    weights: dict[float, int] = {}
    for lines in page_lines:
        for line in lines:
            if line.size > 0:
                key = round(line.size, 1)
                weights[key] = weights.get(key, 0) + len(line.text)
    if not weights:
        return 0.0
    return max(weights.items(), key=lambda item: item[1])[0]


def _lines_to_markdown(lines: list[_PdfLine], body_size: float) -> str:
    """Gắn `#`/`##`/`###` cho tiêu đề và gom dòng bị ngắt thành đoạn văn.

    PDF không có khái niệm "đoạn": mỗi dòng thị giác là một dòng chữ. Xuất thẳng
    từng dòng sang Word thì mỗi dòng thành một paragraph, câu bị chặt giữa chừng.
    Ở đây dòng nào chạm mép phải của cột (chữ tự xuống dòng) thì nối vào đoạn
    đang mở; dòng kết thúc sớm, cách dòng lớn, hoặc là tiêu đề / gạch đầu dòng /
    hàng bảng thì mở đoạn mới.
    """
    if not lines:
        return ""
    lines = _attach_bullet_markers(lines)
    pitch = _line_pitch(lines)
    paragraphs: list[str] = []
    current = ""

    def break_paragraph() -> None:
        nonlocal current
        if current:
            paragraphs.append(current)
            current = ""

    for index, line in enumerate(lines):
        text = line.text.strip()
        level = (
            _heading_level(line.size, body_size)
            if len(text) <= _MAX_HEADING_LINE_CHARS
            else 0
        )
        if level:
            break_paragraph()
            paragraphs.append(f"{'#' * level} {text}")
            continue
        if _STANDALONE_RE.match(text):
            # Gạch đầu dòng vẫn có thể bị ngắt sang dòng sau → mở đoạn mới rồi
            # để các dòng tiếp theo nối vào như đoạn văn thường.
            break_paragraph()
            current = text
            continue
        previous = lines[index - 1] if index else None
        if not current or _starts_paragraph(previous, line, pitch, lines):
            break_paragraph()
            current = text
        else:
            current = _join_wrapped(current, text)
    break_paragraph()
    return "\n".join(paragraphs)


def _attach_bullet_markers(lines: list[_PdfLine]) -> list[_PdfLine]:
    """Gắn ký hiệu gạch đầu dòng đứng riêng vào dòng chữ của nó.

    Trong PDF, dấu "•" thường được vẽ bằng một lượt chữ riêng, có khi nằm cuối
    luồng chữ của trang → pdfium tách nó thành dòng riêng và bản Word xuất ra
    một loạt đoạn chỉ có "•" ở cuối trang. Ở đây dấu được ghép vào dòng gần
    nhất theo trục dọc rồi đưa về đầu dòng chữ đó.
    """
    if not lines:
        return lines
    is_marker = [_BULLET_ONLY_RE.fullmatch(line.text.strip()) for line in lines]
    if not any(is_marker):
        return lines
    texts = [line.text for line in lines]
    claimed: set[int] = set()  # dòng chữ đã nhận một dấu
    attached: set[int] = set()  # dấu đã ghép được vào dòng chữ
    for index, marker in enumerate(lines):
        if is_marker[index] is None:
            continue
        tolerance = max(4.0, marker.size * 0.6)
        same_column = max(40.0, marker.size * 3)
        target = min(
            (
                (abs(line.top - marker.top), other)
                for other, line in enumerate(lines)
                if not is_marker[other]
                and other not in claimed
                and abs(line.top - marker.top) <= tolerance
                and abs(line.left - marker.left) <= same_column
            ),
            default=None,
        )
        if target is None:  # không có dòng chữ cùng dòng kẻ: giữ nguyên dấu
            continue
        claimed.add(target[1])
        attached.add(index)
        texts[target[1]] = f"• {texts[target[1]].strip()}"
    return [
        _PdfLine(texts[index], line.size, line.left, line.right, line.top)
        for index, line in enumerate(lines)
        if index not in attached
    ]


def _line_pitch(lines: list[_PdfLine]) -> float:
    """Nhịp dòng thường của trang = khoảng cách dòng phổ biến nhất."""
    gaps = [
        round(previous.top - line.top, 0)
        for previous, line in zip(lines, lines[1:], strict=False)
        if previous.top > line.top  # bỏ qua dòng cùng mức (bảng nhiều cột)
    ]
    if not gaps:
        return 0.0
    weights: dict[float, int] = {}
    for gap in gaps:
        weights[gap] = weights.get(gap, 0) + 1
    return max(weights.items(), key=lambda item: item[1])[0]


def _starts_paragraph(
    previous: _PdfLine | None, line: _PdfLine, pitch: float, lines: list[_PdfLine]
) -> bool:
    """Dòng này có mở đoạn mới không (dựa vào khoảng cách và mép phải)."""
    if previous is None:
        return True
    if pitch > 0 and (previous.top - line.top) > pitch * _PARAGRAPH_GAP_RATIO:
        return True
    column_right = _column_right_edge(previous, lines)
    if column_right <= 0:
        return False
    # Dòng trước không chạm mép cột → câu đã hết, dòng này là đoạn khác.
    return previous.right < column_right - max(12.0, column_right * 0.02)


def _column_right_edge(line: _PdfLine, lines: list[_PdfLine]) -> float:
    """Mép phải của cột chứa dòng: mép phải lớn nhất của các dòng cùng lề trái."""
    same_column = [
        other.right
        for other in lines
        if abs(other.left - line.left) <= 25.0 and other.right > 0
    ]
    return max(same_column, default=0.0)


def _join_wrapped(current: str, text: str) -> str:
    """Nối dòng bị ngắt giữa câu; gạch nối cuối dòng thì nối liền, giữ gạch."""
    if current.endswith("-"):
        return f"{current}{text}"
    return f"{current} {text}"



def _normalise_heading_levels(pages: list[str]) -> list[str]:
    """Dịch cấp tiêu đề để cấp nông nhất trở thành `#` (Heading 1).

    Ví dụ tài liệu chỉ có 2 cỡ tiêu đề 14pt/12pt (thân 10pt) sẽ ra toàn `##` và
    `###`: mục lục vẫn dựng được nhưng cả cây lùi một cấp so với bản gốc. Dịch
    lên cho cấp ngoài cùng thành `#`, tương quan giữa các cấp giữ nguyên.
    """
    levels = [
        len(match.group(1))
        for page in pages
        for line in page.split("\n")
        if (match := _MARKER_RE.match(line))
    ]
    shift = min(levels, default=1) - 1
    if shift <= 0:
        return pages
    return [
        "\n".join(line[shift:] if _MARKER_RE.match(line) else line for line in page.split("\n"))
        for page in pages
    ]


def _heading_level(size: float, body_size: float) -> int:
    """Cấp tiêu đề suy từ tỉ lệ cỡ chữ (0 = dòng thân văn bản).

    Ngưỡng chọn theo tài liệu thật (thân 10pt): H1 ≈ 18pt (1.8×), H2 ≈ 14pt
    (1.4×), H3 ≈ 12pt (1.2×).
    """
    if size <= 0 or body_size <= 0:
        return 0
    ratio = size / body_size
    if ratio >= 1.7:
        return 1
    if ratio >= 1.3:
        return 2
    if ratio >= 1.12:
        return 3
    return 0


def translate_selection(
    text: str, target_language: str, source_language: str | None = None
) -> str:
    source_hint = (
        f" from {source_language}" if source_language else ""
    )
    return request_anthropic(
        [
            {
                "type": "text",
                "text": (
                    f"Translate accurately{source_hint} into {target_language}. "
                    f"Return the translation only:\n{text[:20000]}"
                ),
            }
        ]
    ).strip()


def answer_question(context: str, question: str) -> str:
    return request_anthropic(
        [{
            "type": "text",
            "text": (
                "You are a document Q&A assistant. Use CONTEXT only. If information is missing, "
                "say that it was not found. Answer in English.\n\n"
                f"CONTEXT:\n{context[:60000]}\n\nCÂU HỎI:\n{question[:4000]}"
            )
        }]
    ).strip()


def make_word_document(text: str, *, title: str | None = None) -> bytes:
    """Xuất văn bản OCR sang .docx **giữ cấu trúc** (heading/outline, bảng, list…).

    Toàn bộ việc parse Markdown nhẹ → style Word nằm ở
    [app.services.docx_service]; hàm này giữ nguyên tên cũ cho nơi gọi.
    """
    return docx_service.to_docx_bytes(text, title=title)


# Loại file đọc được bằng trích xuất text thuần (không cần AI).
_TEXT_MIME_PREFIX = "text/"
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
# Trình duyệt/một số client không nhận diện được đuôi lạ → dò theo tên file.
_TEXT_EXTENSIONS = frozenset({
    ".txt", ".md", ".markdown", ".csv", ".json", ".log", ".xml", ".yml", ".yaml",
    ".py", ".js", ".ts", ".dart", ".java", ".c", ".cpp", ".html", ".css", ".ini",
})


def is_text_extractable(mime_type: str, name: str = "") -> bool:
    """True nếu [extract_document_text] xử lý được loại file này."""
    return (
        mime_type in ("application/pdf", _DOCX_MIME)
        or mime_type.startswith(_TEXT_MIME_PREFIX)
        or name.lower().endswith(tuple(_TEXT_EXTENSIONS))
    )


def extract_document_text(data: bytes, mime_type: str, name: str = "") -> str:
    """Trích văn bản thô từ tài liệu: PDF (pypdf), Word (python-docx),
    các loại text (txt/md/csv/code...) — giải mã utf-8.

    Trả "" nếu không trích được ký tự nào. Ném AIServiceError khi file mã hóa
    hoặc định dạng không hỗ trợ (ảnh_scan cần dùng OCR riêng).
    """
    if not is_text_extractable(mime_type, name):
        raise AIServiceError(
            "This file type cannot be read (supported: PDF, Word, txt/md and plain text)"
        )
    if mime_type == "application/pdf":
        return extract_pdf_text(data)
    if mime_type == _DOCX_MIME:
        try:
            document = WordDocument(io.BytesIO(data))
            return "\n\n".join(
                paragraph.text for paragraph in document.paragraphs if paragraph.text
            ).strip()
        except AIServiceError:
            raise
        except Exception as exc:
            raise AIServiceError("Could not read the Word file content") from exc
    try:
        return data.decode("utf-8", errors="replace").strip()
    except Exception as exc:  # hiếm: decode với replace gần như không fail
        raise AIServiceError("Could not read the text file content") from exc
