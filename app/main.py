from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile, Update
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.clients.backend import backend
from app.config import settings
from app.handlers import customer_router, staff_router
from app.keyboards import markup_from_dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

customer_bot: Bot | None = None
staff_bot: Bot | None = None
customer_dp = Dispatcher()
staff_dp = Dispatcher()
customer_dp.include_router(customer_router)
staff_dp.include_router(staff_router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global customer_bot, staff_bot
    if settings.telegram_customer_bot_token:
        customer_bot = Bot(
            token=settings.telegram_customer_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
    if settings.telegram_staff_bot_token:
        staff_bot = Bot(
            token=settings.telegram_staff_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
    logger.info("Bot service started")
    yield
    if customer_bot:
        await customer_bot.session.close()
    if staff_bot:
        await staff_bot.session.close()
    logger.info("Bot service stopped")


app = FastAPI(title="Simple Travel Telegram Bot", lifespan=lifespan)


def _check_secret(expected: str, incoming: str | None) -> None:
    if not expected:
        return
    if not incoming or not hmac.compare_digest(expected, incoming):
        raise HTTPException(status_code=403, detail="Forbidden")


def _check_service_token(authorization: str | None) -> None:
    if not settings.bot_service_token:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = authorization[7:].strip()
    if not hmac.compare_digest(token, settings.bot_service_token):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
async def health():
    return {"ok": True, "service": "telegram-bot"}


@app.post("/telegram/customer")
async def telegram_customer(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    _check_secret(settings.telegram_customer_webhook_secret, x_telegram_bot_api_secret_token)
    if customer_bot is None:
        raise HTTPException(status_code=503, detail="Customer bot not configured")
    payload = await request.json()
    update = Update.model_validate(payload)
    await customer_dp.feed_update(bot=customer_bot, update=update)
    return {"ok": True}


@app.post("/telegram/staff")
async def telegram_staff(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    _check_secret(settings.telegram_staff_webhook_secret, x_telegram_bot_api_secret_token)
    if staff_bot is None:
        raise HTTPException(status_code=503, detail="Staff bot not configured")
    payload = await request.json()
    update = Update.model_validate(payload)
    await staff_dp.feed_update(bot=staff_bot, update=update)
    return {"ok": True}


@app.post("/internal/notify/")
async def internal_notify(
    request: Request,
    authorization: str | None = Header(default=None),
):
    """Backend Celery → mijozga xabar / hujjat."""
    _check_service_token(authorization)
    if customer_bot is None:
        raise HTTPException(status_code=503, detail="Customer bot not configured")
    body = await request.json()
    kind = body.get("type") or "customer_message"
    chat_id = body.get("chat_id")
    if not chat_id:
        raise HTTPException(status_code=400, detail="chat_id required")

    if kind == "customer_message":
        text = body.get("text") or ""
        markup = markup_from_dict(body.get("reply_markup"))
        await customer_bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
        return {"ok": True}

    if kind == "customer_document":
        url = body.get("download_url")
        caption = body.get("caption") or ""
        if not url:
            raise HTTPException(status_code=400, detail="download_url required")
        content, filename = await backend.download_document(url)
        await customer_bot.send_document(
            chat_id=chat_id,
            document=BufferedInputFile(content, filename=body.get("filename") or filename),
            caption=caption,
        )
        return {"ok": True}

    return JSONResponse({"detail": f"Unknown type: {kind}"}, status_code=400)
