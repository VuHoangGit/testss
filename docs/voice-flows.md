# Luồng chức năng ra lệnh bằng giọng nói tiếng Việt

Tài liệu mô tả các luồng đã triển khai của trợ lý giọng nói trong DocuVault:
STT (Web Speech API) → Gemini Function Calling → thực thi action trên client → TTS phản hồi.

## 1. Luồng tổng quan (push-to-talk đầu cuối)

```mermaid
sequenceDiagram
    actor U as Người dùng
    participant Mic as VoiceMicButton (AppBar)
    participant VC as VoiceController
    participant STT as SpeechService (speech_to_text)
    participant API as FastAPI /ai/voice-command
    participant SVC as VoiceCommandService
    participant GEM as Gemini (function calling)
    participant EXE as VoiceActionExecutor
    participant TTS as TtsService (flutter_tts)

    U->>Mic: Bấm nút mic (user gesture)
    Mic->>VC: toggleMic()
    VC->>STT: initialize() + listen(locale: vi-VN)
    STT-->>VC: interim results (hiển thị "Đang nghe…")
    U->>STT: Nói lệnh tiếng Việt
    STT-->>VC: Kết quả final (transcript)
    VC->>API: POST transcript + context (tên tab/folder/tài liệu) + session_id
    API->>SVC: interpret()
    SVC->>GEM: prompt hệ thống + function declarations
    GEM-->>SVC: functionCall {action, params} hoặc text
    SVC-->>API: VoiceCommandResponse (đã validate)
    API-->>VC: VoiceCommandResult
    VC->>EXE: executeVoiceAction(ref, decision)
    EXE-->>VC: Câu phản hồi cuối
    VC-->>U: Hiển thị trên VoicePanel
    VC->>TTS: speak(phản hồi) — nếu TTS bật
    TTS-->>U: Đọc phản hồi bằng tiếng Việt
```

## 2. Luồng backend — Gemini Function Calling

```mermaid
flowchart TD
    A[POST /ai/voice-command<br/>transcript + context + session_id] --> B[Xây prompt hệ thống:<br/>danh sách 13 action + tên tab/folder/tài liệu<br/>KHÔNG gửi id]
    B --> C[Gọi generateContent<br/>kèm tools.functionDeclarations]
    C --> D{Gemini trả về gì?}
    D -- functionCall --> E{Action + params<br/>hợp lệ?}
    E -- Có --> F[Trả VoiceCommandResponse<br/>action + params + reply]
    E -- Không<br/>enum sai / thiếu param --> G[Trả kèm lỗi trong reply<br/>không thực thi]
    D -- Chỉ text --> H[Trả reply dạng hội thoại<br/>action = null]
    D -- Lỗi infra<br/>timeout / không key / 5xx --> I[Ném VoiceCommandError<br/>API trả 503 + thông báo tiếng Việt]
    F --> J[Ghi lịch sử hội thoại<br/>tối đa 10 lượt / session]
```

Điểm chính:
- **Whitelist 13 action**: `navigate_tab`, `open_ai_tool`, `select_folder`, `list_documents`, `open_document`, `run_ocr`, `ask_chat`, `translate_text`, `read_aloud`, `stop_speaking`, `delete_document`, `merge_documents`, `split_document`.
- Gemini chỉ thấy **tên** thư mục/tài liệu — không bao giờ thấy id; việc ánh xạ tên → id làm ở client nên AI không thể "mò" id.
- Lịch sử hội thoại giữ in-memory theo `session_id` (tối đa 10 lượt) để hỗ trợ lệnh tiếp theo kiểu "mở file vừa rồi".

## 3. Luồng thực thi action + resolve tên tài liệu (client)

```mermaid
flowchart TD
    A[executeVoiceAction] --> B{Action}
    B -- navigate_tab / open_ai_tool --> C[Đổi tab provider<br/>đóng PDF viewer nếu đang mở]
    B -- list_documents / select_folder --> D[Lọc / đọc danh sách<br/>từ DocumentsController]
    B -- open_document / run_ocr /<br/>ask_chat / translate_text --> E[Gọi repository tương ứng<br/>cập nhật state AI]
    B -- read_aloud / stop_speaking --> F[Đọc kết quả gần nhất / dừng TTS]
    B -- delete / merge / split --> G[Nhóm cần xác nhận — xem luồng 4]
    B -- Action lạ --> H[Không thực thi,<br/>trả "chưa được hỗ trợ"]
```

```mermaid
flowchart TD
    A[Tham số tên tài liệu<br/>vd: "hợp đồng"] --> B[name_matcher:<br/>bỏ dấu tiếng Việt, chuẩn hóa]
    B --> C{Kết quả khớp}
    C -- Unique --> D[Dùng tài liệu đó]
    C -- Ambiguous<br/>nhiều file gần giống --> E[Trả lời liệt kê các ứng viên,<br/>yêu cầu nói lại tên đủ]
    C -- None --> F["Không tìm thấy tài liệu" + gợi ý gần giống]
    E --> G[Người dùng nói lại → lặp lại luồng]
```

## 4. Luồng hành động phá hủy (xóa / gộp / tách) — luôn xác nhận

```mermaid
sequenceDiagram
    actor U as Người dùng
    participant EXE as VoiceActionExecutor
    participant DLG as Dialog (root navigator)

    U->>EXE: "xóa file hợp đồng"
    EXE->>EXE: resolve tên → tài liệu (unique)
    alt Không khớp duy nhất
        EXE-->>U: Yêu cầu nói lại tên chính xác (dừng)
    else Khớp duy nhất
        EXE->>DLG: AlertDialog "Xóa tài liệu?" + tên file
        DLG-->>U: Bấm "Xóa" hoặc "Hủy"
        alt Bấm Xóa
            DLG->>EXE: true → gọi deleteDocument(id)
            EXE-->>U: "Đã xóa …"
        else Bấm Hủy / đóng dialog
            EXE-->>U: "Đã hủy lệnh xóa."
        end
    end
```

- **Gộp (merge)**: resolve từng tên → nếu thiếu <2 PDF thì yêu cầu nói lại; dialog tự điền tên file gộp (AI có thể gợi ý `new_name`) → người dùng sửa/bấm tay.
- **Tách (split)**: dialog tự điền dải trang (`ranges`) từ params AI → người dùng duyệt rồi mới thực thi.

## 5. Luồng lỗi

```mermaid
flowchart TD
    A[Lỗi] --> B{Loại}
    B -- Không cấp quyền micro --> C[Gợi ý mở cài đặt trình duyệt,<br/>chỉ dùng ô nhập văn bản]
    B -- Không nghe rõ<br/>transcript < 2 ký tự --> D["Không nghe rõ, bạn thử nói lại nhé"]
    B -- Backend 503<br/>không có GEMINI_API_KEY / lỗi Gemini --> E[Thông báo lỗi tiếng Việt,<br/>đề xuất thử lại]
    B -- Lỗi khi thực thi action<br/>vd OCR fail --> F["Thao tác thất bại: …"<br/>không crash app]
    B -- Mic không khả dụng<br/>trình duyệt không hỗ trợ --> G[micAvailable = false,<br/>vẫn nhập lệnh bằng văn bản]
```

Mọi lỗi đều được bắt trong `VoiceController` / `executeVoiceAction` — app không bao giờ crash vì lệnh giọng nói.

## 6. Fallback nhập lệnh bằng văn bản

Khi mic không dùng được (không cấp quyền, trình duyệt không hỗ trợ Web Speech API) hoặc người dùng không muốn nói, VoicePanel có ô nhập lệnh: gõ `"vào tab tài liệu"`, `"quét OCR file hợp đồng"`… → đi thẳng vào `_process()` giống transcript từ mic (bỏ qua bước STT).
