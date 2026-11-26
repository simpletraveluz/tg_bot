from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class BackendClient:
    def __init__(self) -> None:
        self.base = settings.backend_url.rstrip("/")
        self.headers = {}
        if settings.bot_service_token:
            self.headers["Authorization"] = f"Bearer {settings.bot_service_token}"

    async def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        url = f"{self.base}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(method, url, headers=self.headers, **kwargs)
            if response.status_code >= 400:
                logger.warning("Backend %s %s → %s %s", method, path, response.status_code, response.text[:300])
                try:
                    data = response.json()
                except Exception:
                    data = {"detail": response.text}
                data["_status"] = response.status_code
                return data
            if not response.content:
                return {}
            return response.json()

    async def otp_request(self, chat_id: str, phone: str, role: str) -> dict:
        return await self._request(
            "POST",
            "/bot/otp/request/",
            json={"chat_id": chat_id, "phone": phone, "role": role},
        )

    async def otp_verify(self, chat_id: str, code: str, role: str) -> dict:
        return await self._request(
            "POST",
            "/bot/otp/verify/",
            json={"chat_id": chat_id, "code": code, "role": role},
        )

    async def orders_lookup(self, phone: str, token: str = "") -> dict:
        return await self._request(
            "POST",
            "/bot/orders/lookup/",
            json={"phone": phone, "token": token},
        )

    async def orders_bind(self, chat_id: str, phone: str, order_ids: list[int] | None = None) -> dict:
        return await self._request(
            "POST",
            "/bot/orders/bind/",
            json={"chat_id": chat_id, "phone": phone, "order_ids": order_ids or []},
        )

    async def customer_documents(self, chat_id: str) -> dict:
        return await self._request("GET", f"/bot/customers/{chat_id}/documents/")

    async def customer_context(self, chat_id: str) -> dict:
        return await self._request("GET", f"/bot/customers/{chat_id}/context/")

    async def customer_bound(self, chat_id: str) -> dict:
        return await self._request("GET", f"/bot/customers/{chat_id}/bound/")

    async def staff_by_phone(self, phone: str) -> dict:
        return await self._request("GET", "/bot/staff/by-phone/", params={"phone": phone})

    async def staff_by_chat(self, chat_id: str) -> dict:
        return await self._request("GET", f"/bot/staff/by-chat/{chat_id}/")

    async def staff_link(self, user_id: int, chat_id: str) -> dict:
        return await self._request(
            "POST",
            "/bot/staff/telegram-link/",
            json={"user_id": user_id, "chat_id": chat_id},
        )

    async def staff_targets(self, chat_id: str) -> dict:
        return await self._request("GET", "/bot/staff/targets/", params={"chat_id": chat_id})

    async def download_document(self, download_url: str) -> tuple[bytes, str]:
        """Absolute URL from Backend documents list."""
        headers = dict(self.headers)
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(download_url, headers=headers)
            response.raise_for_status()
            name = "document.pdf"
            cd = response.headers.get("content-disposition") or ""
            if "filename=" in cd:
                name = cd.split("filename=")[-1].strip().strip('"')
            return response.content, name


backend = BackendClient()
