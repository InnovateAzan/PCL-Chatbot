from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import get_settings  # noqa: E402
from backend.app.integrations.microsoft.obo_service import OnBehalfOfService  # noqa: E402
from backend.app.integrations.microsoft.sharepoint_client import SharePointClient  # noqa: E402
from backend.app.services.onedesk.field_mapping import get_live_it_ticket_field_mapping  # noqa: E402


async def main() -> None:
    settings = get_settings()
    user_token = os.getenv("ONEASSIST_ACCESS_TOKEN", "").strip()

    print(f"authentication configured: {bool(settings.enable_entra_auth and settings.azure_client_id)}")
    print(f"OBO configured: {bool(settings.azure_client_secret and settings.azure_obo_scopes)}")
    print(f"site URL configured: {bool(settings.onedesk_site_url)}")
    print(f"list configured: {settings.effective_it_service_desk_list_id or settings.effective_it_service_desk_list_title}")

    if not user_token:
        print("Set ONEASSIST_ACCESS_TOKEN to run a live connection check.")
        return

    graph_token = await OnBehalfOfService().exchange(user_token)
    client = SharePointClient(access_token=graph_token)
    site = await client.resolve_site(settings.onedesk_site_url)
    site_id = str(site.get("id") or settings.effective_onedesk_site_id)
    list_id = settings.effective_it_service_desk_list_id
    if not list_id:
        list_info = await client.get_list_by_title(
            site_id,
            settings.effective_it_service_desk_list_title,
        )
        list_id = str((list_info or {}).get("id") or "")

    columns = await client.get_list_columns(site_id, list_id)
    mapping = get_live_it_ticket_field_mapping(columns)

    print(f"site resolved: {bool(site_id)}")
    print(f"list resolved: {bool(list_id)}")
    print(f"list ID: {list_id}")
    print(f"column count: {len(columns)}")
    print("discovered internal mappings:")
    for key, value in mapping.__dict__.items():
        print(f"  {key}: {value or '(missing)'}")


if __name__ == "__main__":
    asyncio.run(main())
