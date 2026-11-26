from __future__ import annotations

import logging
import re

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.clients.backend import backend
from app.keyboards import contact_keyboard, main_keyboard
from app.state import redis_store as store

logger = logging.getLogger(__name__)
router = Router(name="customer")


def _digits_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("998") and len(digits) == 12:
        return digits
    if len(digits) == 9:
        return f"998{digits}"
    return digits if len(digits) >= 9 else ""


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    chat_id = str(message.chat.id)
    parts = (message.text or "").split(maxsplit=1)
    token = parts[1].strip() if len(parts) > 1 else ""
    await store.save_customer_state(chat_id, state="idle", pending_token=token)
    await message.answer(
        "Assalomu alaykum! Bronni ulash uchun telefon raqamingizni yuboring.",
        reply_markup=contact_keyboard(),
    )


@router.message(F.contact)
async def on_contact(message: Message) -> None:
    phone = _digits_phone(message.contact.phone_number if message.contact else "")
    await _request_otp(message, phone)


@router.message(F.text == "Mening hujjatlarim")
async def on_docs(message: Message, bot: Bot) -> None:
    chat_id = str(message.chat.id)
    bound = await backend.customer_bound(chat_id)
    if not bound.get("bound"):
        await message.answer("Avval bronni ulashing. Telefon yuboring.", reply_markup=contact_keyboard())
        return
    data = await backend.customer_documents(chat_id)
    docs = data.get("documents") or []
    if not docs:
        await message.answer("Hujjatlar hali yuklanmagan.", reply_markup=main_keyboard())
        return
    for doc in docs:
        url = doc.get("download_url")
        if not url:
            continue
        try:
            content, filename = await backend.download_document(url)
            await bot.send_document(
                chat_id=message.chat.id,
                document=BufferedInputFile(content, filename=doc.get("filename") or filename),
                caption=doc.get("title") or "",
            )
        except Exception:
            logger.exception("document send failed")
            await message.answer(f"Hujjat yuklanmadi: {doc.get('title')}")


@router.message(F.text == "Admin ga yozish")
async def on_admin_chat(message: Message) -> None:
    chat_id = str(message.chat.id)
    bound = await backend.customer_bound(chat_id)
    if not bound.get("bound"):
        await message.answer("Avval bronni ulashing. Telefon yuboring.", reply_markup=contact_keyboard())
        return
    await store.save_customer_state(chat_id, state="wait_chat")
    await message.answer("Menejerga xabaringizni yozing.")


@router.callback_query(F.data.startswith("arr:"))
async def on_arrival(callback: CallbackQuery) -> None:
    await callback.answer()
    data = callback.data or ""
    parts = data.split(":")
    if len(parts) != 3:
        return
    _, kind, _order_id = parts
    chat_id = str(callback.message.chat.id) if callback.message else ""
    if kind in ("yes", "ok"):
        if callback.message:
            await callback.message.answer("Rahmat! Yaxshi dam oling.", reply_markup=main_keyboard())
        return
    if chat_id:
        await store.save_customer_state(chat_id, state="wait_chat")
    if callback.message:
        await callback.message.answer("Muammoni yozib yuboring, menejer javob beradi.")


@router.message(F.text)
async def on_text(message: Message, bot: Bot) -> None:
    chat_id = str(message.chat.id)
    text = (message.text or "").strip()
    if text in ("Mening hujjatlarim", "Admin ga yozish") or text.startswith("/"):
        return

    state = await store.get_customer_state(chat_id)

    if state.get("state") == "wait_otp":
        result = await backend.otp_verify(chat_id, text, "customer")
        if result.get("_status", 200) >= 400 or not result.get("ok"):
            await message.answer("Kod noto‘g‘ri yoki muddati o‘tgan. /start qilib qayta urinib ko‘ring.")
            return
        phone = result.get("phone") or ""
        pending = state.get("pending_token") or ""
        await store.save_customer_state(chat_id, state="idle", phone=phone)
        lookup = await backend.orders_lookup(phone, pending)
        orders = lookup.get("orders") or []
        if not orders:
            await message.answer(
                "Bu raqam bo‘yicha bron topilmadi. Menejeringiz bilan bog‘laning.",
                reply_markup=main_keyboard(),
            )
            return
        bind = await backend.orders_bind(chat_id, phone, [o["id"] for o in orders])
        orders = bind.get("orders") or orders
        names = ", ".join(
            (o.get("hotel_name") or o.get("title") or f"#{o['id']}") for o in orders[:3]
        )
        await message.answer(f"Bron ulandi: {names}.", reply_markup=main_keyboard())
        return

    if state.get("state") == "wait_chat":
        delivered = await _forward_to_staff(bot, chat_id, text)
        await store.save_customer_state(chat_id, state="idle")
        if delivered:
            await message.answer("Xabaringiz menejerga yuborildi.", reply_markup=main_keyboard())
        return

    phone = _digits_phone(text)
    if phone:
        await _request_otp(message, phone)
        return

    await message.answer("Menyu tugmalaridan foydalaning.", reply_markup=main_keyboard())


async def _request_otp(message: Message, phone: str) -> None:
    if not phone:
        await message.answer("Telefon raqamini to‘g‘ri yuboring.", reply_markup=contact_keyboard())
        return
    chat_id = str(message.chat.id)
    result = await backend.otp_request(chat_id, phone, "customer")
    if result.get("_status") == 429:
        await message.answer(result.get("detail") or "Kod yaqinda yuborilgan. Biroz kuting.")
        return
    if result.get("_status", 200) >= 400:
        await message.answer(result.get("detail") or "SMS yuborilmadi. Keyinroq urinib ko‘ring.")
        return
    await store.save_customer_state(chat_id, state="wait_otp")
    await message.answer("SMS orqali kelgan 4 xonali kodni yuboring.")


async def _forward_to_staff(bot: Bot, customer_chat_id: str, text: str) -> bool:
    from app.config import settings

    targets = await backend.staff_targets(customer_chat_id)
    header = (
        f"Mijoz: {targets.get('customer_phone') or customer_chat_id}\n"
        f"Bron: #{targets.get('order_id') or '-'}\n"
        f"{targets.get('order_title') or ''}\n\n{text}"
    )
    staff_list = targets.get("targets") or []
    if not staff_list or not settings.telegram_staff_bot_token:
        await bot.send_message(
            chat_id=int(customer_chat_id),
            text="Menejer hozir Telegramda emas. Tez orada javob beramiz.",
            reply_markup=main_keyboard(),
        )
        return False
    staff_bot = Bot(token=settings.telegram_staff_bot_token)
    try:
        for staff in staff_list:
            sent = await staff_bot.send_message(chat_id=staff["chat_id"], text=header)
            await store.map_staff_message(
                str(staff["chat_id"]), str(sent.message_id), customer_chat_id
            )
            await store.set_last_customer(str(staff["chat_id"]), customer_chat_id)
    finally:
        await staff_bot.session.close()
    return True
