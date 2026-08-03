from __future__ import annotations

import asyncio
from typing import Any

import httpx

from backend.app.core.config import get_settings
from backend.app.integrations.microsoft.graph_errors import (
    GraphClientError,
    GraphConfigurationError,
    GraphErrorDetail,
)


class GraphClient:
    def __init__(self, access_token: str | None = None) -> None:
        self.settings = get_settings()
        self.access_token = access_token
        self.base_url = self.settings.graph_base_url.rstrip("/")

    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, *, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("POST", path, json_body=json_body)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.access_token:
            raise GraphConfigurationError("Graph access token is not available.")

        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        attempts = 3

        async with httpx.AsyncClient(timeout=15.0) as client:
            for attempt in range(1, attempts + 1):
                try:
                    response = await client.request(
                        method,
                        url,
                        params=params,
                        json=json_body,
                        headers=headers,
                    )
                except httpx.TimeoutException as exc:
                    if attempt == attempts:
                        raise GraphClientError(
                            GraphErrorDetail(504, "Microsoft Graph request timed out.", retryable=True)
                        ) from exc
                    await asyncio.sleep(attempt)
                    continue

                if response.status_code in {429, 500, 502, 503, 504} and attempt < attempts:
                    retry_after = response.headers.get("Retry-After")
                    delay = int(retry_after) if retry_after and retry_after.isdigit() else attempt
                    await asyncio.sleep(delay)
                    continue

                if response.is_error:
                    raise GraphClientError(
                        GraphErrorDetail(
                            status_code=response.status_code,
                            message="Microsoft Graph request failed.",
                            retryable=response.status_code in {429, 500, 502, 503, 504},
                            details=_safe_error_payload(response),
                        )
                    )

                return response.json() if response.content else {}

        raise GraphClientError(GraphErrorDetail(500, "Microsoft Graph request failed.", retryable=True))


def _safe_error_payload(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {"status_code": response.status_code}

    if isinstance(payload, dict):
        return payload
    return {"status_code": response.status_code}
