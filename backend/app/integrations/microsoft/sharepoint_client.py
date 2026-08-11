from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from backend.app.core.config import get_settings
from backend.app.integrations.microsoft.graph_client import GraphClient


# ---------------------------------------------------------------------
# SharePoint / Microsoft Graph field configuration
# ---------------------------------------------------------------------

IT_TICKET_FIELDS: tuple[str, ...] = (
    "SerialNumber",
    "Title",
    "Status",
    "Assignedto0",
    "Assignedto0LookupId",
    "RequestType",
    "Author",
    "AuthorLookupId",
    "NatureofComplain",
    "Created",
    "Modified",
)

GRAPH_LIST_ITEM_FIELDS: tuple[str, ...] = (
    "id",
    "createdBy",
    "createdDateTime",
    "lastModifiedDateTime",
)


class SharePointClient:
    def __init__(self, access_token: str | None = None) -> None:
        self.settings = get_settings()
        self.graph = GraphClient(access_token=access_token)

    async def resolve_site(
        self,
        site_url: str | None = None,
    ) -> dict[str, Any]:
        url = (
            site_url
            or self.settings.onedesk_site_url
            or self.settings.sharepoint_site_url
        )

        parts = urlsplit(url)

        if not parts.hostname:
            return {}

        path = parts.path.strip("/")

        graph_path = (
            f"sites/{parts.hostname}:/{path}"
            if path
            else f"sites/{parts.hostname}"
        )

        return await self.graph.get(graph_path)

    async def list_lists(
        self,
        site_id: str,
    ) -> list[dict[str, Any]]:
        payload = await self.graph.get(
            f"sites/{site_id}/lists"
        )

        return list(payload.get("value") or [])

    async def get_list_by_title(
        self,
        site_id: str,
        title: str,
    ) -> dict[str, Any] | None:
        wanted_title = str(title or "").strip().lower()

        for item in await self.list_lists(site_id):
            display_name = str(
                item.get("displayName") or ""
            ).strip().lower()

            if display_name == wanted_title:
                return item

        return None

    async def get_list_columns(
        self,
        site_id: str,
        list_id: str,
    ) -> list[dict[str, Any]]:
        payload = await self.graph.get(
            f"sites/{site_id}/lists/{list_id}/columns"
        )

        return list(payload.get("value") or [])

    async def get_list_content_types(
        self,
        site_id: str,
        list_id: str,
    ) -> list[dict[str, Any]]:
        payload = await self.graph.get(
            f"sites/{site_id}/lists/{list_id}/contentTypes"
        )

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
        """
        Read SharePoint list items through Microsoft Graph.

        Important:
        Custom SharePoint fields such as SerialNumber and Assignedto0
        belong inside:

            $expand=fields($select=...)

        They must NOT be placed in the top-level $select because Graph's
        listItem object does not expose those custom columns directly.
        """

        # If the caller provides SharePoint field names, use them only
        # inside the fields expansion.
        custom_fields = _normalize_custom_fields(selected_fields)

        params: dict[str, str] = {
            "$top": str(top),

            # Custom SharePoint columns
            "$expand": (
                "fields($select="
                + ",".join(custom_fields)
                + ")"
            ),

            # Valid Microsoft Graph listItem properties only
            "$select": ",".join(GRAPH_LIST_ITEM_FIELDS),
        }

        if filter_query:
            params["$filter"] = filter_query

        payload = await self.graph.get(
            f"sites/{site_id}/lists/{list_id}/items",
            params=params,
        )

        return list(payload.get("value") or [])

    async def get_list_item(
        self,
        site_id: str,
        list_id: str,
        item_id: int | str,
        *,
        selected_fields: list[str] | None = None,
    ) -> dict[str, Any] | None:
        item_id_text = str(item_id or "").strip()

        if not item_id_text:
            return None

        custom_fields = _normalize_custom_fields(selected_fields)

        params: dict[str, str] = {
            "$expand": (
                "fields($select="
                + ",".join(custom_fields)
                + ")"
            ),
            "$select": ",".join(GRAPH_LIST_ITEM_FIELDS),
        }

        payload = await self.graph.get(
            f"sites/{site_id}/lists/{list_id}/items/{item_id_text}",
            params=params,
        )

        return payload if isinstance(payload, dict) else None

    async def create_list_item(
        self,
        site_id: str,
        list_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        return await self.graph.post(
            f"sites/{site_id}/lists/{list_id}/items",
            json_body={
                "fields": fields,
            },
        )

    # -----------------------------------------------------------------
    # SharePoint User Information List
    # -----------------------------------------------------------------

    async def get_user_information_list(
        self,
        site_id: str,
    ) -> dict[str, Any] | None:
        """
        Find SharePoint's User Information List.

        Person/Group columns may be returned from Graph as:

            Assignedto0LookupId = 22

        The lookup ID can then be resolved to a readable user name.
        """

        lists = await self.list_lists(site_id)

        possible_names = {
            "user information list",
            "user information",
        }

        for item in lists:
            display_name = str(
                item.get("displayName") or ""
            ).strip().lower()

            name = str(
                item.get("name") or ""
            ).strip().lower()

            if (
                display_name in possible_names
                or name in possible_names
            ):
                return item

        return None

    async def get_site_user_by_lookup_id(
        self,
        site_id: str,
        lookup_id: int | str,
    ) -> dict[str, Any] | None:
        lookup_text = str(lookup_id or "").strip()

        if not lookup_text:
            return None

        user_list = await self.get_user_information_list(site_id)

        if not user_list:
            return None

        user_list_id = str(
            user_list.get("id") or ""
        ).strip()

        if not user_list_id:
            return None

        payload = await self.graph.get(
            f"sites/{site_id}/lists/{user_list_id}/items/{lookup_text}",
            params={
                "$expand": "fields",
                "$select": "id,createdDateTime,lastModifiedDateTime",
            },
        )

        if not isinstance(payload, dict):
            return None

        fields = payload.get("fields")

        return fields if isinstance(fields, dict) else None

    async def resolve_person_lookup_name(
        self,
        site_id: str,
        lookup_id: int | str,
    ) -> str | None:
        """
        Resolve a SharePoint Person/Group lookup ID to a readable name.
        """

        fields = await self.get_site_user_by_lookup_id(
            site_id,
            lookup_id,
        )

        if not fields:
            return None

        for key in (
            "Title",
            "displayName",
            "DisplayName",
            "Name",
            "EMail",
            "Email",
            "UserName",
        ):
            value = fields.get(key)

            if str(value or "").strip():
                return str(value).strip()

        return None


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _normalize_custom_fields(
    selected_fields: list[str] | None,
) -> list[str]:
    """
    Return only SharePoint custom field names for fields($select=...).

    Graph top-level properties such as id and createdBy are deliberately
    excluded because they belong in the outer $select.
    """

    if not selected_fields:
        return list(IT_TICKET_FIELDS)

    graph_top_level = {
        field.lower()
        for field in GRAPH_LIST_ITEM_FIELDS
    }

    result: list[str] = []

    for raw_field in selected_fields:
        field = str(raw_field or "").strip()

        if not field:
            continue

        if field.lower() in graph_top_level:
            continue

        if field not in result:
            result.append(field)

    # The OneDesk ticket service requires these fields. Add missing ones
    # even if the caller passed only part of the schema.
    for field in IT_TICKET_FIELDS:
        if field not in result:
            result.append(field)

    return result


class MockSharePointClient:
    async def resolve_site(
        self,
        site_url: str | None = None,
    ) -> dict[str, Any]:
        return {
            "id": "mock-site-id",
            "displayName": "Mock IT HelpDesk2",
            "webUrl": (
                site_url
                or "https://mock.invalid/sites/ITHelpDesk2"
            ),
            "mode": "mock",
        }

    async def list_lists(
        self,
        site_id: str,
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": "mock-it-service-desk-list-id",
                "displayName": "Issue tracker",
                "webUrl": "https://mock.invalid/lists/issue-tracker",
                "mode": "mock",
            },
            {
                "id": "mock-user-information-list-id",
                "displayName": "User Information List",
                "webUrl": "https://mock.invalid/lists/user-information",
                "mode": "mock",
            },
        ]

    async def get_list_by_title(
        self,
        site_id: str,
        title: str,
    ) -> dict[str, Any] | None:
        wanted_title = str(title or "").strip().lower()

        for item in await self.list_lists(site_id):
            display_name = str(
                item.get("displayName") or ""
            ).strip().lower()

            if display_name == wanted_title:
                return item

        return None

    async def get_list_columns(
        self,
        site_id: str,
        list_id: str,
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": "mock-serial-number",
                "name": "SerialNumber",
                "displayName": "Serial Number",
                "number": {},
                "required": True,
                "readOnly": False,
                "hidden": False,
                "mode": "mock",
            },
            {
                "id": "mock-title",
                "name": "Title",
                "displayName": "Title",
                "text": {
                    "maxLength": 255,
                },
                "required": True,
                "readOnly": False,
                "hidden": False,
                "mode": "mock",
            },
            {
                "id": "mock-status",
                "name": "Status",
                "displayName": "Status",
                "choice": {
                    "choices": [
                        "New",
                        "Open",
                        "In Progress",
                        "Resolved",
                        "Closed",
                    ],
                },
                "required": False,
                "readOnly": False,
                "hidden": False,
                "mode": "mock",
            },
            {
                "id": "mock-assigned-to",
                "name": "Assignedto0",
                "displayName": "Assigned to",
                "personOrGroup": {},
                "required": False,
                "readOnly": False,
                "hidden": False,
                "mode": "mock",
            },
            {
                "id": "mock-request-type",
                "name": "RequestType",
                "displayName": "Request_Type",
                "choice": {
                    "choices": [
                        "Application Rights Request",
                        "Network & Infrastructure Support",
                        "Application Support",
                        "Application Change Request",
                    ],
                },
                "required": False,
                "readOnly": False,
                "hidden": False,
                "mode": "mock",
            },
            {
                "id": "mock-author",
                "name": "Author",
                "displayName": "Created By",
                "personOrGroup": {},
                "required": False,
                "readOnly": True,
                "hidden": False,
                "mode": "mock",
            },
        ]

    async def get_list_content_types(
        self,
        site_id: str,
        list_id: str,
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": "mock-content-type",
                "name": "Item",
                "mode": "mock",
            }
        ]

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

                # Required for ownership filtering.
                "createdBy": {
                    "user": {
                        "displayName": "Mock User",
                        "email": "mock.user@example.com",
                        "userPrincipalName": "mock.user@example.com",
                        "id": "mock-user-id",
                    }
                },

                "createdDateTime": "2026-05-20T08:00:00Z",
                "lastModifiedDateTime": "2026-06-24T10:00:00Z",

                "fields": {
                    "SerialNumber": 113,
                    "Title": "Mock laptop support request",
                    "Status": "Resolved",
                    "Assignedto0LookupId": 22,
                    "RequestType": "Network & Infrastructure Support",
                    "AuthorLookupId": 10,
                    "NatureofComplain": "Network",
                    "Created": "2026-05-20T08:00:00Z",
                    "Modified": "2026-06-24T10:00:00Z",
                },

                "mode": "mock",
            }
        ][:top]

    async def get_list_item(
        self,
        site_id: str,
        list_id: str,
        item_id: int | str,
        *,
        selected_fields: list[str] | None = None,
    ) -> dict[str, Any] | None:
        items = await self.get_list_items(
            site_id,
            list_id,
            top=100,
            selected_fields=selected_fields,
        )

        wanted = str(item_id)

        for item in items:
            if str(item.get("id")) == wanted:
                return item

        return None

    async def create_list_item(
        self,
        site_id: str,
        list_id: str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "id": "mock-created-item",
            "fields": fields,
            "mode": "mock",
        }

    async def get_user_information_list(
        self,
        site_id: str,
    ) -> dict[str, Any] | None:
        return {
            "id": "mock-user-information-list-id",
            "displayName": "User Information List",
            "mode": "mock",
        }

    async def get_site_user_by_lookup_id(
        self,
        site_id: str,
        lookup_id: int | str,
    ) -> dict[str, Any] | None:
        if str(lookup_id).strip() == "22":
            return {
                "Title": "Mock Assigned User",
                "EMail": "assigned.user@example.com",
            }

        return None

    async def resolve_person_lookup_name(
        self,
        site_id: str,
        lookup_id: int | str,
    ) -> str | None:
        fields = await self.get_site_user_by_lookup_id(
            site_id,
            lookup_id,
        )

        if not fields:
            return None

        for key in (
            "Title",
            "displayName",
            "DisplayName",
            "Name",
            "EMail",
            "Email",
            "UserName",
        ):
            value = fields.get(key)

            if str(value or "").strip():
                return str(value).strip()

        return None