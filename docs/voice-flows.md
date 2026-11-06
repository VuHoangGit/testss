# English voice command flows

This document describes the implemented flows of the DocuVault voice assistant:
STT (Web Speech API, `en-US`) → LLM tool use → client-side action execution → TTS reply.
Everything the user hears or reads from the assistant is English.

## 1. End-to-end push-to-talk flow

```mermaid
sequenceDiagram
    actor U as User
    participant Mic as VoiceMicButton (AppBar)
    participant VC as VoiceController
    participant STT as SpeechService (speech_to_text, en-US)
    participant API as FastAPI /ai/voice-command
    participant SVC as VoiceCommandService
    participant LLM as Anthropic Messages API (tool use)
    participant EXE as VoiceActionExecutor
    participant TTS as TtsService (flutter_tts, en-US)

    U->>Mic: Press the mic button (user gesture)
    Mic->>VC: toggleMic()
    VC->>STT: initialize() + listen(locale: en-US)
    STT-->>VC: interim results ("Listening…")
    U->>STT: Say an English command
    STT-->>VC: final transcript
    VC->>API: POST transcript + context (tab/folder/document names) + session_id
    API->>SVC: interpret()
    SVC->>LLM: system prompt + tool declarations
    LLM-->>SVC: tool_use {name, input} or plain text
    SVC-->>API: VoiceCommandResponse (validated)
    API-->>VC: VoiceCommandResult
    VC->>EXE: executeVoiceAction(ref, decision)
    EXE-->>VC: final reply sentence
    VC-->>U: Shown in VoicePanel
    VC->>TTS: speak(reply) — when TTS is enabled
    TTS-->>U: Reads the reply in English
```

## 2. Backend — LLM tool use

```mermaid
flowchart TD
    A[POST /ai/voice-command<br/>transcript + context + session_id] --> B[Build system prompt:<br/>13 actions + tab/folder/document names<br/>NEVER sends ids]
    B --> C[Call the Messages endpoint<br/>with tools.functionDeclarations]
    C --> D{What did the model return?}
    D -- tool_use --> E{Action + params<br/>valid?}
    E -- Yes --> F[Return VoiceCommandResponse<br/>action + params + reply]
    E -- No<br/>bad enum / missing param --> G[Return the error in reply<br/>nothing is executed]
    D -- Text only --> H[Return a conversational reply<br/>action = null]
    D -- Infra error<br/>timeout / no token / 5xx --> I[Raise VoiceCommandError<br/>API returns 503 + English message]
    F --> J[Store conversation history<br/>max 10 turns per session]
```

Key points:
- **13-action whitelist**: `navigate_tab`, `open_ai_tool`, `select_folder`, `list_documents`, `open_document`, `run_ocr`, `ask_chat`, `translate_text`, `read_aloud`, `stop_speaking`, `delete_document`, `merge_documents`, `split_document`.
- The model only sees folder/document **names** — never ids; name → id mapping happens on the client, so the AI cannot guess ids.
- Conversation history is kept in memory per `session_id` (max 10 turns) so follow-ups like "open the file I just mentioned" work.
- Provider config lives in `.env`: `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, `ANTHROPIC_MODEL`.

## 3. Client — action execution and document name resolution

```mermaid
flowchart TD
    A[executeVoiceAction] --> B{Action}
    B -- navigate_tab / open_ai_tool --> C[Switch tab provider<br/>close the PDF viewer if open]
    B -- list_documents / select_folder --> D[Filter / read the list<br/>from DocumentsController]
    B -- open_document / run_ocr /<br/>ask_chat / translate_text --> E[Call the matching repository<br/>update AI state]
    B -- read_aloud / stop_speaking --> F[Read the latest result / stop TTS]
    B -- delete / merge / split --> G[Needs confirmation — see flow 4]
    B -- Unknown action --> H[Nothing executed,<br/>reply "not supported by voice"]
```

```mermaid
flowchart TD
    A[Document name parameter<br/>e.g. "contract"] --> B[name_matcher:<br/>strip Vietnamese diacritics, normalize]
    B --> C{Match result}
    C -- Unique --> D[Use that document]
    C -- Ambiguous<br/>several similar files --> E[Reply with the candidates,<br/>ask for the full name]
    C -- None --> F["No document named …" + similar names]
    E --> G[User repeats the command → flow restarts]
```

## 4. Destructive actions (delete / merge / split) — always confirmed

```mermaid
sequenceDiagram
    actor U as User
    participant EXE as VoiceActionExecutor
    participant DLG as Dialog (root navigator)

    U->>EXE: "delete the contract file"
    EXE->>EXE: resolve name → document (unique)
    alt Not a unique match
        EXE-->>U: Ask for the exact name (stop)
    else Unique match
        EXE->>DLG: AlertDialog "Delete document?" + file name
        DLG-->>U: Press "Delete" or "Cancel"
        alt Pressed Delete
            DLG->>EXE: true → deleteDocument(id)
            EXE-->>U: "Deleted …"
        else Pressed Cancel / dismissed
            EXE-->>U: "Delete cancelled."
        end
    end
```

- **Merge**: resolves each name → if fewer than 2 PDFs, asks again; the dialog pre-fills the merged file name (the model may suggest `new_name`) → the user reviews or edits it.
- **Split**: the dialog pre-fills the page `ranges` from the model params → the user reviews before it runs.

## 5. Error flows

```mermaid
flowchart TD
    A[Error] --> B{Type}
    B -- Microphone permission denied --> C[Point to browser settings,<br/>fall back to the text box]
    B -- Not understood<br/>transcript < 2 chars --> D["I did not catch that, please try again."]
    B -- Backend 503<br/>missing token / provider error --> E[English error message,<br/>suggest retrying]
    B -- Action failed<br/>e.g. OCR error --> F["Action failed: …"<br/>app never crashes]
    B -- Microphone unavailable<br/>browser unsupported --> G[micAvailable = false,<br/>text commands still work]
```

Every error is caught inside `VoiceController` / `executeVoiceAction` — the app never crashes because of a voice command.

## 6. Text-command fallback

When the mic is unavailable (permission denied, browser without Web Speech API) or the user prefers typing,
VoicePanel offers a text field: type `"go to the documents tab"`, `"run OCR on the contract file"`, …
Those commands go straight into `_process()` exactly like a mic transcript (the STT step is skipped).
