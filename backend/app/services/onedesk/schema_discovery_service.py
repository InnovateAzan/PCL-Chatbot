from __future__ import annotations

from typing import Any

from backend.app.core.config import get_settings
from backend.app.integrations.microsoft.graph_errors import GraphConfigurationError
from backend.app.integrations.microsoft.sharepoint_client import (
    MockSharePointClient,
    SharePointClient,
)
from backend.app.services.onedesk.field_mapping import get_it_service_desk_field_mapping


class OneDeskSchemaDiscoveryService:
    def __init__(self, *, access_token: str | None = None) -> None:
        self.settings = get_settings()
        self.mode = "mock" if self._should_use_mock(access_token) else "live"
        self.client = (
            MockSharePointClient()
            if self.mode == "mock"
            else SharePointClient(access_token=access_token)
        )

    async def site(self) -> dict[str, Any]:
        site = await self.client.resolve_site(self.settings.onedesk_site_url)
        return {
            "mode": self.mode,
            "site": _safe_public_dict(site),
            "configuredSiteUrl": self.settings.onedesk_site_url,
        }

    async def lists(self) -> dict[str, Any]:
        site_id = await self._site_id()
        lists = await self.client.list_lists(site_id)
        return {
            "mode": self.mode,
            "siteId": site_id,
            "lists": [_safe_public_dict(item) for item in lists],
        }

    async def it_service_desk_schema(self) -> dict[str, Any]:
        site_id = await self._site_id()
        list_info = await self._it_service_desk_list(site_id)
        list_id = str(list_info.get("id") or "")
        columns = await self.client.get_list_columns(site_id, list_id)
        content_types = await self.client.get_list_content_types(site_id, list_id)

        return {
            "mode": self.mode,
            "warning": (
                "Mock values are placeholders; do not use mock internal names for production mapping."
                if self.mode == "mock"
                else None
            ),
            "siteId": site_id,
            "listId": list_id,
            "listDisplayName": list_info.get("displayName"),
            "configuredFieldMapping": get_it_service_desk_field_mapping(),
            "columns": [self._format_column(column) for column in columns],
            "contentTypes": [_safe_public_dict(item) for item in content_types],
        }

    async def sample_items(self, *, top: int = 5) -> dict[str, Any]:
        site_id = await self._site_id()
        list_info = await self._it_service_desk_list(site_id)
        list_id = str(list_info.get("id") or "")
        items = await self.client.get_list_items(site_id, list_id, top=top)
        return {
            "mode": self.mode,
            "siteId": site_id,
            "listId": list_id,
            "items": [_safe_public_dict(item) for item in items],
        }

    async def _site_id(self) -> str:
        configured = self.settings.effective_onedesk_site_id
        if configured:
            return configured
        site = await self.client.resolve_site(self.settings.onedesk_site_url)
        site_id = str(site.get("id") or "")
        if not site_id:
            raise GraphConfigurationError("OneDesk SharePoint site ID could not be resolved.")
        return site_id

    async def _it_service_desk_list(self, site_id: str) -> dict[str, Any]:
        configured_id = self.settings.effective_it_service_desk_list_id
        if configured_id:
            return {
                "id": configured_id,
                "displayName": self.settings.effective_it_service_desk_list_title,
            }

        list_info = await self.client.get_list_by_title(
            site_id,
            self.settings.effective_it_service_desk_list_title,
        )
        if not list_info:
            raise GraphConfigurationError("IT Service Desk list could not be resolved.")
        return list_info

    def _should_use_mock(self, access_token: str | None) -> bool:
        if self.settings.enable_onedesk_mock_mode:
            return True
        return not (
            access_token
            and self.settings.enable_onedesk_schema_discovery
            and (self.settings.effective_onedesk_site_id or self.settings.onedesk_site_url)
        )

    @staticmethod
    def _format_column(column: dict[str, Any]) -> dict[str, Any]:
        column_type = _detect_column_type(column)
        choice = column.get("choice") or {}
        person = column.get("personOrGroup") or {}
        text = column.get("text") or {}
        return {
            "id": column.get("id"),
            "displayName": column.get("displayName"),
            "internalName": column.get("name"),
            "type": column_type,
            "required": bool(column.get("required")),
            "readOnly": bool(column.get("readOnly")),
            "hidden": bool(column.get("hidden")),
            "choiceValues": choice.get("choices") or [],
            "personColumn": person or None,
            "defaultValue": column.get("defaultValue"),
            "maximumLength": text.get("maxLength"),
            "mode": column.get("mode"),
        }


def _detect_column_type(column: dict[str, Any]) -> str:
    for key in (
        "text",
        "choice",
        "personOrGroup",
        "dateTime",
        "number",
        "boolean",
        "lookup",
        "hyperlinkOrPicture",
    ):
        if key in column:
            return key
    return "unknown"


def _safe_public_dict(value: dict[str, Any]) -> dict[str, Any]:
    blocked_tokens = {"token", "secret", "password", "authorization"}
    safe: dict[str, Any] = {}
    for key, item in value.items():
        lowered = key.lower()
        if any(token in lowered for token in blocked_tokens):
            continue
        if isinstance(item, dict):
            safe[key] = _safe_public_dict(item)
        elif isinstance(item, list):
            safe[key] = [
                _safe_public_dict(child) if isinstance(child, dict) else child
                for child in item
            ]
        else:
            safe[key] = item
    return safe
