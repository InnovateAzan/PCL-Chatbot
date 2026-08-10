from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from backend.app.core.config import get_settings
from backend.app.integrations.microsoft.graph_errors import (
    GraphClientError,
    GraphConfigurationError,
    GraphErrorDetail,
)
from backend.app.core.logging_config import log_event, sanitize_log_data


logger = logging.getLogger(__name__)


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
                started = time.perf_counter()
                log_event(
                    logger,
                    "graph_request_started",
                    method=method,
                    path=_safe_graph_path(path),
                    operation=_graph_operation(path),
                    attempt=attempt,
                )
                try:
                    response = await client.request(
                        method,
                        url,
                        params=params,
                        json=json_body,
                        headers=headers,
                    )
                except httpx.TimeoutException as exc:
                    duration_ms = round((time.perf_counter() - started) * 1000, 2)
                    log_event(
                        logger,
                        "graph_request_timeout",
                        level=logging.WARNING,
                        method=method,
                        path=_safe_graph_path(path),
                        operation=_graph_operation(path),
                        attempt=attempt,
                        duration_ms=duration_ms,
                    )
                    if attempt == attempts:
                        raise GraphClientError(
                            GraphErrorDetail(504, "Microsoft Graph request timed out.", retryable=True)
                        ) from exc
                    await asyncio.sleep(attempt)
                    continue

                if response.status_code in {429, 500, 502, 503, 504} and attempt < attempts:
                    retry_after = response.headers.get("Retry-After")
                    delay = int(retry_after) if retry_after and retry_after.isdigit() else attempt
                    log_event(
                        logger,
                        "graph_request_retry",
                        level=logging.WARNING,
                        method=method,
                        path=_safe_graph_path(path),
                        operation=_graph_operation(path),
                        status=response.status_code,
                        retry_after=retry_after,
                        attempt=attempt,
                    )
                    await asyncio.sleep(delay)
                    continue

                if response.is_error:
                    duration_ms = round((time.perf_counter() - started) * 1000, 2)
                    safe_error = _safe_error_payload(response)
                    log_event(
                        logger,
                        "graph_request_failed",
                        level=logging.WARNING,
                        method=method,
                        path=_safe_graph_path(path),
                        operation=_graph_operation(path),
                        status=response.status_code,
                        duration_ms=duration_ms,
                        graph_error_code=_graph_error_code(safe_error),
                        graph_error_message=_graph_error_message(safe_error),
                        request_id=response.headers.get("request-id"),
                        client_request_id=response.headers.get("client-request-id"),
                    )
                    raise GraphClientError(
                        GraphErrorDetail(
                            status_code=response.status_code,
                            message="Microsoft Graph request failed.",
                            retryable=response.status_code in {429, 500, 502, 503, 504},
                            details=_safe_error_payload(response),
                        )
                    )

                duration_ms = round((time.perf_counter() - started) * 1000, 2)
                log_event(
                    logger,
                    "graph_request_completed",
                    method=method,
                    path=_safe_graph_path(path),
                    operation=_graph_operation(path),
                    status=response.status_code,
                    duration_ms=duration_ms,
                    attempt=attempt,
                    request_id=response.headers.get("request-id"),
                    client_request_id=response.headers.get("client-request-id"),
                )
                return response.json() if response.content else {}

        raise GraphClientError(GraphErrorDetail(500, "Microsoft Graph request failed.", retryable=True))


def _safe_error_payload(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {"status_code": response.status_code}

    if isinstance(payload, dict):
        return sanitize_log_data(payload)
    return {"status_code": response.status_code}


def _safe_graph_path(path: str) -> str:
    return path.split("?", 1)[0][:500]


def _graph_operation(path: str) -> str:
    normalized = path.lower()
    if "/columns" in normalized:
        return "list_columns"
    if "/items" in normalized:
        return "list_items"
    if normalized.startswith("sites/"):
        if "/lists" in normalized:
            return "sharepoint_list"
        return "sharepoint_site"
    return "graph_request"


def _graph_error_code(payload: dict[str, Any]) -> str | None:
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("code") or "") or None
    return str(payload.get("code") or "") or None


def _graph_error_message(payload: dict[str, Any]) -> str | None:
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or "")[:300] or None
    return str(payload.get("message") or "")[:300] or None
