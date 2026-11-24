# DocuVault backend — FastAPI + psycopg3 + LibreOffice (DOC→DOCX forms).
# Render build: root directory `backend/`, dockerfile path `Dockerfile`.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# LibreOffice (soffice) — only needed for legacy .doc form templates.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-writer \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts
COPY form_templates ./form_templates

# Non-root user for the running process.
RUN useradd --create-home appuser \
    && mkdir -p /app/storage/documents \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Render passes PORT; default 8000 keeps local docker runs working.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
