from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from backend.app.core.config import get_settings
from backend.app.integrations.microsoft.graph_client import GraphClient


class SharePointClient:
    def __init__(self, access_token: str | None = None) -> None:
        self.settings = get_settings()
        self.graph = GraphClient(access_token=access_token)

    async def resolve_site(self, site_url: str | None = None) -> dict[str, Any]:
        url = site_url or self.settings.onedesk_site_url or self.settings.sharepoint_site_url
        parts = urlsplit(url)
        if not parts.hostname:
            return {}
        path = parts.path.strip("/")
        graph_path = f"sites/{parts.hostname}:/{path}" if path else f"sites/{parts.hostname}"
        return await self.graph.get(graph_path)

    async def list_lists(self, site_id: str) -> list[dict[str, Any]]:
        payload = await self.graph.get(f"sites/{site_id}/lists")
        return list(payload.get("value") or [])

    async def get_list_by_title(self, site_id: str, title: str) -> dict[str, Any] | None:
        for item in await self.list_lists(site_id):
            if str(item.get("displayName") or "").lower() == title.lower():
                return item
        return None

    async def get_list_columns(self, site_id: str, list_id: str) -> list[dict[str, Any]]:
        payload = await self.graph.get(f"sites/{site_id}/lists/{list_id}/columns")
        return list(payload.get("value") or [])

    async def get_list_content_types(self, site_id: str, list_id: str) -> list[dict[str, Any]]:
        payload = await self.graph.get(f"sites/{site_id}/lists/{list_id}/contentTypes")
        return list(payload.get("value") or [])

    async def get_list_items(
        self,
        site_id: str,
        list_id: str,
        *,
        top: int = 5,
        selected_fields: list[str] | None = None,
        filter_query: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {
            "$top": str(top),
            "expand": "fields",
        }
        if selected_fields:
            params["$select"] = ",".join(selected_fields)
        if filter_query:
            params["$filter"] = filter_query
        payload = await self.graph.get(f"sites/{site_id}/lists/{list_id}/items", params=params)
        return list(payload.get("value") or [])

    async def create_list_item(
        self,
        site_id: str,
        list_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.graph.post(
            f"sites/{site_id}/lists/{list_id}/items",
            json_body={"fields": fields},
        )


class MockSharePointClient:
    async def resolve_site(self, site_url: str | None = None) -> dict[str, Any]:
        return {
            "id": "mock-site-id",
            "displayName": "Mock IT HelpDesk2",
            "webUrl": site_url or "https://mock.invalid/sites/ITHelpDesk2",
            "mode": "mock",
        }

    async def list_lists(self, site_id: str) -> list[dict[str, Any]]:
        return [
            {
                "id": "mock-it-service-desk-list-id",
                "displayName": "Issue tracker",
                "webUrl": "https://mock.invalid/lists/issue-tracker",
                "mode": "mock",
            }
        ]

    async def get_list_by_title(self, site_id: str, title: str) -> dict[str, Any] | None:
        return (await self.list_lists(site_id))[0]

    async def get_list_columns(self, site_id: str, list_id: str) -> list[dict[str, Any]]:
        return [
            {
                "id": "mock-title",
                "name": "MOCK_DO_NOT_USE_Title",
                "displayName": "Title",
                "text": {"maxLength": 255},
                "required": True,
                "readOnly": False,
                "hidden": False,
                "mode": "mock",
            },
            {
                "id": "mock-status",
                "name": "MOCK_DO_NOT_USE_Status",
                "displayName": "Status",
                "choice": {"choices": ["Open", "In Progress", "Closed"]},
                "required": False,
                "readOnly": False,
                "hidden": False,
                "mode": "mock",
            },
        ]

    async def get_list_content_types(self, site_id: str, list_id: str) -> list[dict[str, Any]]:
        return [{"id": "mock-content-type", "name": "Item", "mode": "mock"}]

    async def get_list_items(
        self,
        site_id: str,
        list_id: str,
        *,
        top: int = 5,
        selected_fields: list[str] | None = None,
        filter_query: str | None = None,
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": "1",
                "fields": {
                    "Title": "Mock laptop support request",
                    "MOCK_DO_NOT_USE_Status": "Open",
                },
                "mode": "mock",
            }
        ][:top]
