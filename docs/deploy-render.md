# Huong dan deploy backend DocuVault len Render (0d)

> Tai lieu noi bo cho Thanh — cac buoc bam tren dashboard.
> nhanh dang dung: `feat/credits-sepay-payments`

## Chuan bi (da xong, khong lam lai)

- DB Supabase Postgres da dung schema + seed pricing (11 bang), pooler
  `aws-0-ap-southeast-1.pooler.supabase.com:6543` — da test ket noi +
  smoke test order/webhook PASS.
- Dockerfile + render.yaml + form_templates/ da vao repo (cho Render build).
- Luu tru file: giai doan 1 dung o dia Render — file upload co the mat khi
  service sleep/redeploy (demo do an chap nhan; sau nay chuyen Supabase
  Storage thi ben).

## Buoc 1 — Push code

```powershell
git push origin feat/credits-sepay-payments
```

## Buoc 2 — Tao service tren Render (5 phut)

1. Dang ky render.com bang GitHub → New → **Blueprint** → chon repo
   DocVaultProject → Render doc `backend/render.yaml`, hoi dien cac bien
   `sync: false`.
2. Dien tung bien theo bang o Buoc 3.
3. Bam Create → cho build Docker (~5 phut lan dau, cai LibreOffice).

## Buoc 3 — Bien moi truong

Xem file `deploy-render-env.md` cung thu muc: bang bien bat buoc + tuy chon.
