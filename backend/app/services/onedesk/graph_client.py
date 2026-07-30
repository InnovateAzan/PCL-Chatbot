from __future__ import annotations

import httpx

from backend.app.core.config import get_settings
from backend.app.services.onedesk.base_client import OneDeskListConfig


class GraphOneDeskClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def query_user_records(
        self,
        *,
        config: OneDeskListConfig,
        user_email: str,
        request_number: str | None,
        access_token: str | None = None,
        limit: int = 5,
    ) -> list[dict]:
        if not access_token:
            return []

        if not self.settings.sharepoint_site_id or not config.list_id:
            return []

        filters = [f"fields/{config.user_email_field} eq '{user_email}'"]
        if request_number:
            filters.append(
                f"fields/{config.request_number_field} eq '{request_number}'"
            )

        url = (
            f"{self.settings.graph_base_url}/sites/{self.settings.sharepoint_site_id}"
            f"/lists/{config.list_id}/items"
        )
        params = {
            "expand": "fields",
            "$top": str(limit),
            "$filter": " and ".join(filters),
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            payload = response.json()

        return [item.get("fields", {}) for item in payload.get("value", [])]
