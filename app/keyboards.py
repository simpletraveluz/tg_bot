from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Mening hujjatlarim")],
            [KeyboardButton(text="Admin ga yozish")],
        ],
        resize_keyboard=True,
    )


def contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Telefonni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def arrival_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Ha", callback_data=f"arr:yes:{order_id}"),
                InlineKeyboardButton(text="Ok", callback_data=f"arr:ok:{order_id}"),
                InlineKeyboardButton(
                    text="Yo‘q, muammolar bor", callback_data=f"arr:no:{order_id}"
                ),
            ]
        ]
    )


def markup_from_dict(data: dict | None):
    """Backend/Celery dan kelgan reply_markup dict → aiogram markup."""
    if not data:
        return None
    if "inline_keyboard" in data:
        rows = []
        for row in data["inline_keyboard"]:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=btn.get("text", ""),
                        callback_data=btn.get("callback_data"),
                    )
                    for btn in row
                ]
            )
        return InlineKeyboardMarkup(inline_keyboard=rows)
    if "keyboard" in data:
        rows = []
        for row in data["keyboard"]:
            buttons = []
            for btn in row:
                if isinstance(btn, dict):
                    buttons.append(
                        KeyboardButton(
                            text=btn.get("text", ""),
                            request_contact=btn.get("request_contact", False),
                        )
                    )
                else:
                    buttons.append(KeyboardButton(text=str(btn)))
            rows.append(buttons)
        return ReplyKeyboardMarkup(
            keyboard=rows,
            resize_keyboard=bool(data.get("resize_keyboard", True)),
        )
    return None
