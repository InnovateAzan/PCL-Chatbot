from __future__ import annotations

from typing import Any

import httpx

from backend.app.core.config import get_settings


class OneDeskApiClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = self.settings.onedesk_api_base_url.rstrip("/")
        self.api_token = self.settings.onedesk_api_token

    def _headers(self) -> dict[str, str]:
        return {
            "X-Api-Token": self.api_token,
            "Content-Type": "application/json",
        }

    async def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{self.base_url}/{endpoint.lstrip('/')}",
                headers=self._headers(),
                params=params,
            )
            response.raise_for_status()
            return response.json()

    async def post(
        self,
        endpoint: str,
        payload: dict[str, Any],
    ) -> Any:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{self.base_url}/{endpoint.lstrip('/')}",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return response.json()