from __future__ import annotations

import logging
import re

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.clients.backend import backend
from app.config import settings
from app.keyboards import contact_keyboard, main_keyboard
from app.state import redis_store as store

logger = logging.getLogger(__name__)
router = Router(name="staff")


def _digits_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("998") and len(digits) == 12:
        return digits
    if len(digits) == 9:
        return f"998{digits}"
    return digits if len(digits) >= 9 else ""


async def _ensure_linked(chat_id: str) -> dict:
    """Redis + Backend dan staff ulanish holatini sinxronlash."""
    st = await store.get_staff_state(chat_id)
    if st.get("linked") and st.get("user_id"):
        return st
    remote = await backend.staff_by_chat(chat_id)
    if remote.get("linked") and remote.get("id"):
        return await store.save_staff_state(
            chat_id, linked=True, user_id=remote["id"], pending_phone=""
        )
    return st


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    chat_id = str(message.chat.id)
    st = await _ensure_linked(chat_id)
    if st.get("linked"):
        await message.answer("Siz allaqachon ulangan. Mijoz xabarlariga reply qiling.")
        return
    await message.answer("Menejer boti. Ish telefoningizni yuboring.", reply_markup=contact_keyboard())


@router.message(F.contact)
async def on_contact(message: Message) -> None:
    phone = _digits_phone(message.contact.phone_number if message.contact else "")
    await _start_staff_otp(message, phone)


@router.message(F.text.regexp(r"^\d{4}$"))
async def on_otp(message: Message) -> None:
    chat_id = str(message.chat.id)
    st = await _ensure_linked(chat_id)
    if st.get("linked"):
        return
    result = await backend.otp_verify(chat_id, message.text or "", "staff")
    if result.get("_status", 200) >= 400 or not result.get("ok"):
        await message.answer("Kod noto‘g‘ri. /start qilib qayta urinib ko‘ring.")
        return
    phone = result.get("phone") or st.get("pending_phone") or ""
    user = await backend.staff_by_phone(phone)
    if user.get("_status") == 404 or not user.get("id"):
        await message.answer("Bu raqam xodim hisobiga ulanmagan.")
        return
    link = await backend.staff_link(int(user["id"]), chat_id)
    if link.get("_status", 200) >= 400:
        await message.answer("Ulanishda xatolik.")
        return
    name = " ".join(p for p in [user.get("first_name"), user.get("last_name")] if p).strip() or phone
    await store.save_staff_state(chat_id, linked=True, user_id=user["id"], pending_phone="")
    await message.answer(f"Ulandi: {name}. Mijoz xabarlariga reply qiling.")


@router.message(F.reply_to_message)
async def on_reply(message: Message) -> None:
    chat_id = str(message.chat.id)
    st = await _ensure_linked(chat_id)
    if not st.get("linked"):
        await message.answer("Avval telefon orqali ulaning.", reply_markup=contact_keyboard())
        return
    reply = message.reply_to_message
    if reply is None:
        return
    customer_chat = await store.resolve_reply(chat_id, str(reply.message_id))
    if not customer_chat:
        await message.answer("Qaysi mijozga javob ekanini reply qilib yuboring.")
        return
    text = (message.text or "").strip()
    if not text:
        return
    await _deliver_to_customer(customer_chat, text)
    await message.answer("Javob yuborildi.")


@router.message(F.text)
async def on_text(message: Message) -> None:
    chat_id = str(message.chat.id)
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return
    if re.fullmatch(r"\d{4}", text):
        return

    st = await _ensure_linked(chat_id)

    if st.get("linked"):
        customer_chat = await store.get_last_customer(chat_id)
        if customer_chat and text:
            await _deliver_to_customer(customer_chat, text)
            await message.answer("Javob mijozga yuborildi.")
            return
        await message.answer("Telefon yuboring yoki mijoz xabariga reply qiling.")
        return

    phone = _digits_phone(text)
    if phone:
        await _start_staff_otp(message, phone)
        return

    await message.answer("Telefon yuboring yoki mijoz xabariga reply qiling.", reply_markup=contact_keyboard())


async def _start_staff_otp(message: Message, phone: str) -> None:
    if not phone:
        await message.answer("Telefon raqamini to‘g‘ri yuboring.", reply_markup=contact_keyboard())
        return
    chat_id = str(message.chat.id)
    user = await backend.staff_by_phone(phone)
    if user.get("_status") == 404 or not user.get("id"):
        await message.answer("Bu raqam xodim hisobiga ulanmagan.")
        return
    result = await backend.otp_request(chat_id, phone, "staff")
    if result.get("_status") == 429:
        await message.answer(result.get("detail") or "Kod yaqinda yuborilgan.")
        return
    if result.get("_status", 200) >= 400:
        await message.answer(result.get("detail") or "SMS yuborilmadi.")
        return
    await store.save_staff_state(chat_id, pending_phone=phone, linked=False)
    await message.answer("SMS kodni yuboring.")


async def _deliver_to_customer(customer_chat_id: str, text: str) -> None:
    if not settings.telegram_customer_bot_token:
        return
    bot = Bot(token=settings.telegram_customer_bot_token)
    try:
        await bot.send_message(
            chat_id=customer_chat_id,
            text=f"Menejer: {text}",
            reply_markup=main_keyboard(),
        )
    finally:
        await bot.session.close()
