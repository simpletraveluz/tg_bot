# Simple Travel — Telegram Bot Service

Alohida deploy: customer + staff botlar. Business ma’lumotlar Backend `/api/v1/bot/*` orqali.

## Stack

- FastAPI + aiogram 3 + httpx + Redis
- Docker Compose (`bot` + `redis`)

## Tez start

```bash
cp .env.example .env
# .env ni to'ldiring
docker compose up -d --build
```

Health: `GET /health`

## Webhook

```bash
# Customer
curl "https://api.telegram.org/bot$TELEGRAM_CUSTOMER_BOT_TOKEN/setWebhook" \
  -d "url=https://YOUR_BOT_HOST/telegram/customer" \
  -d "secret_token=$TELEGRAM_CUSTOMER_WEBHOOK_SECRET"

# Staff
curl "https://api.telegram.org/bot$TELEGRAM_STAFF_BOT_TOKEN/setWebhook" \
  -d "url=https://YOUR_BOT_HOST/telegram/staff" \
  -d "secret_token=$TELEGRAM_STAFF_WEBHOOK_SECRET"
```

Cutover dan keyin Backendda: `TELEGRAM_LEGACY_WEBHOOKS=0`

## Env (Backend ham)

- `BOT_SERVICE_TOKEN` — ikkala tomonda bir xil
- `BOT_SERVICE_URL` — Celery notify uchun (`https://YOUR_BOT_HOST`)
- `TELEGRAM_LEGACY_WEBHOOKS=0` — Django webhook 410; bot service ishga tushgach

## Endpoints

| Method | Path | Kim |
|--------|------|-----|
| GET | `/health` | probe |
| POST | `/telegram/customer` | Telegram |
| POST | `/telegram/staff` | Telegram |
| POST | `/internal/notify/` | Backend Celery (`Bearer BOT_SERVICE_TOKEN`) |
