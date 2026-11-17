"""Do nhanh key AI (AQ.*) hoat dong voi endpoint/model nao.

Chay: ./.venv/Scripts/python.exe scripts/test_ai_key.py
Script thu tung ung vien (endpoint x model) va in ket qua — khong sua gi het.
Key doc tu backend/.env, khong in ra man hinh.
"""

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def read_token() -> str:
    for line in (Path(__file__).resolve().parent.parent / ".env").read_text(
        encoding="utf-8"
    ).splitlines():
        if line.startswith("ANTHROPIC_AUTH_TOKEN="):
            return line.split("=", 1)[1].strip()
    print("!! Khong thay ANTHROPIC_AUTH_TOKEN trong backend/.env")
    sys.exit(1)


def anthropic_post(url: str, token: str, model: str) -> tuple[int, str]:
    """POST 1 loi chat Anthropic Messages toi url, tra (status, body rut gon)."""
    response = requests.post(
        url,
        headers={
            "x-api-key": token,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 16,
            "messages": [{"role": "user", "content": "Reply with OK only"}],
        },
        timeout=30,
    )
    return response.status_code, response.text[:300]


def gemini_native(token: str) -> tuple[int, str]:
    """API goc cua Gemini (generateContent) — chung minh key con song."""
    response = requests.post(
        "https://generativelanguage.googleapis.com/v1beta/models"
        "/gemini-2.5-flash:generateContent",
        headers={"x-goog-api-key": token, "content-type": "application/json"},
        json={"contents": [{"parts": [{"text": "Reply with OK only"}]}]},
        timeout=30,
    )
    return response.status_code, response.text[:300]


def main() -> None:
    token = read_token()
    masked = f"{token[:6]}...{token[-4:]}"
    print(f"Key: {masked}\n")

    cases: list[tuple[str, str]] = [
        (
            "Google anthropic-compat /apps (model claude)",
            "https://generativelanguage.googleapis.com/apps/anthropic-api/v1/messages",
            "claude-sonnet-4-5",
        ),
        (
            "Google anthropic-compat /apps (model gemini)",
            "https://generativelanguage.googleapis.com/apps/anthropic-api/v1/messages",
            "gemini-2.5-pro",
        ),
        (
            "Vertex anthropic-api (model claude)",
            "https://aiplatform.googleapis.com/anthropic-api/v1/messages",
            "claude-sonnet-4-5",
        ),
    ]
    for label, url, model in cases:
        try:
            status, body = anthropic_post(url, token, model)
        except requests.RequestException as exc:
            print(f"[LOI KET NOI] {label}: {type(exc).__name__}: {exc}\n")
            continue
        mark = "OK " if status == 200 else "FAIL"
        print(f"[{mark} {status}] {label}\n  {body}\n")

    try:
        status, body = gemini_native(token)
    except requests.RequestException as exc:
        print(f"[LOI KET NOI] Gemini native: {type(exc).__name__}: {exc}")
        return
    mark = "OK " if status == 200 else "FAIL"
    print(f"[{mark} {status}] Gemini native generateContent (do key song)\n  {body}")


if __name__ == "__main__":
    main()
