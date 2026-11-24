# Bien moi truong Render (copy tung dong)

> `<DB_PASSWORD>` = password DB Supabase (dang dung: dat lai trong
> Project Settings → Database neu quen). `<ten-app>` = ten service dat
> tren Render (vd docuvault-api → domain docuvault-api.onrender.com).

## Nhom bat buoc

```
DATABASE_URL=postgresql+psycopg://postgres.coryhhxuexvnqkdgkvtj:<DB_PASSWORD>@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres
SUPABASE_URL=https://coryhhxuexvnqkdgkvtj.supabase.co
ANTHROPIC_AUTH_TOKEN=<token Gemini AQ.… tu backend/.env>
ANTHROPIC_BASE_URL=https://generativelanguage.googleapis.com
ANTHROPIC_MODEL=gemini-3-flash-preview
OCR_VISION_MODEL=gemini-3-flash-preview
SEPAY_WEBHOOK_SECRET=<secret tu backend/.env>
SEPAY_BANK_ACCOUNT=1998609039999
SEPAY_BANK_BIN=MB
SEPAY_ACCOUNT_NAME=VU MINH HOANG
```

## Nhom production (sau khi biet domain)

```
ENVIRONMENT=production
TRUSTED_HOSTS=<ten-app>.onrender.com
CORS_ORIGINS=https://<ten-app>.onrender.com
PUBLIC_WEB_BASE_URL=https://<ten-app>.onrender.com
FORM_TEMPLATES_DIR=/app/form_templates
```

## Nhom tuy chon (co default trong code, khong bat buoc)

```
ANTHROPIC_TIMEOUT_SECONDS=90
MAX_UPLOAD_MB=50
USER_STORAGE_QUOTA_MB=1024
CREDIT_COST_AI=50
PLAN_QUOTA_FREE=300
PLAN_QUOTA_PLUS=1000
PLAN_QUOTA_PRO=2500
PLAN_QUOTA_MAX=10000
```

## Sau khi deploy — 2 viec nho

1. SePay → webhook URL: `https://<ten-app>.onrender.com/api/v1/payments/sepay/webhook`.
2. Test khoi dong: mo `https://<ten-app>.onrender.com/openapi.json` → thay JSON la chay.
