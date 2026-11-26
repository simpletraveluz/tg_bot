from __future__ import annotations

import json
from typing import Any

import redis.asyncio as redis

from app.config import settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def set_json(key: str, value: dict[str, Any], ttl: int = 86400 * 7) -> None:
    await get_redis().set(key, json.dumps(value, ensure_ascii=False), ex=ttl)


async def get_json(key: str) -> dict[str, Any] | None:
    raw = await get_redis().get(key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def delete_key(key: str) -> None:
    await get_redis().delete(key)


# Customer FSM
def customer_key(chat_id: str) -> str:
    return f"tg:customer:{chat_id}"


async def get_customer_state(chat_id: str) -> dict[str, Any]:
    data = await get_json(customer_key(chat_id))
    return data or {"state": "idle", "pending_token": "", "phone": ""}


async def save_customer_state(chat_id: str, **fields: Any) -> dict[str, Any]:
    current = await get_customer_state(chat_id)
    current.update(fields)
    await set_json(customer_key(chat_id), current)
    return current


# Staff pending OTP phone
def staff_key(chat_id: str) -> str:
    return f"tg:staff:{chat_id}"


async def get_staff_state(chat_id: str) -> dict[str, Any]:
    data = await get_json(staff_key(chat_id))
    return data or {"linked": False, "user_id": None, "pending_phone": ""}


async def save_staff_state(chat_id: str, **fields: Any) -> dict[str, Any]:
    current = await get_staff_state(chat_id)
    current.update(fields)
    await set_json(staff_key(chat_id), current)
    return current


# Reply mapping: staff_chat_id + message_id → customer chat_id
def reply_key(staff_chat_id: str, message_id: str) -> str:
    return f"tg:reply:{staff_chat_id}:{message_id}"


async def map_staff_message(staff_chat_id: str, message_id: str, customer_chat_id: str) -> None:
    await set_json(reply_key(staff_chat_id, message_id), {"customer_chat_id": customer_chat_id}, ttl=86400 * 30)


async def resolve_reply(staff_chat_id: str, message_id: str) -> str | None:
    data = await get_json(reply_key(staff_chat_id, message_id))
    if not data:
        return None
    return data.get("customer_chat_id")


# Last open conversation per staff chat (fallback without reply)
def last_conv_key(staff_chat_id: str) -> str:
    return f"tg:lastconv:{staff_chat_id}"


async def set_last_customer(staff_chat_id: str, customer_chat_id: str) -> None:
    await set_json(last_conv_key(staff_chat_id), {"customer_chat_id": customer_chat_id}, ttl=86400)


async def get_last_customer(staff_chat_id: str) -> str | None:
    data = await get_json(last_conv_key(staff_chat_id))
    return (data or {}).get("customer_chat_id")
