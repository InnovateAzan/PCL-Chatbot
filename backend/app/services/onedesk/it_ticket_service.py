from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from backend.app.core.config import get_settings
from backend.app.integrations.microsoft.graph_errors import (
    GraphClientError,
    GraphConfigurationError,
)
from backend.app.integrations.microsoft.obo_service import OnBehalfOfService
from backend.app.integrations.microsoft.sharepoint_client import SharePointClient
from backend.app.security.entra_auth import AuthenticatedUser
from backend.app.services.onedesk.field_mapping import (
    ItTicketFieldMapping,
    get_live_it_ticket_field_mapping,
)


OPEN_STATUSES = {"new", "blocked", "in progress", "reopen", "incomplete", "pending"}
CLOSED_STATUSES = {"resolved", "closed"}
SUPPORTED_STATUSES = OPEN_STATUSES | CLOSED_STATUSES


class ItTicketConfigurationError(RuntimeError):
    pass


class ItTicketPermissionError(RuntimeError):
    pass


class ItTicketTemporaryError(RuntimeError):
    pass


@dataclass(frozen=True)
class NormalizedItTicket:
    serial_number: int | str
    title: str | None
    status: str | None
    assigned_to: str
    priority: str | None
    request_type: str | None
    nature_of_complaint: str | None
    created_at: str | None
    modified_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ItTicketService:
    def __init__(self, *, access_token: str | None = None) -> None:
        self.settings = get_settings()
        self.user_access_token = access_token
        self._client: SharePointClient | None = None
        self._site_id: str | None = None
        self._list_id: str | None = None
        self._mapping: ItTicketFieldMapping | None = None

    async def get_user_tickets(self, current_user: AuthenticatedUser) -> list[dict[str, Any]]:
        tickets = await self._owned_tickets(current_user)
        return [ticket.to_dict() for ticket in tickets]

    async def get_open_tickets(self, current_user: AuthenticatedUser) -> list[dict[str, Any]]:
        return [
            ticket.to_dict()
            for ticket in await self._owned_tickets(current_user)
            if _normalize_status(ticket.status) in OPEN_STATUSES
        ]

    async def get_closed_tickets(self, current_user: AuthenticatedUser) -> list[dict[str, Any]]:
        return [
            ticket.to_dict()
            for ticket in await self._owned_tickets(current_user)
            if _normalize_status(ticket.status) in CLOSED_STATUSES
        ]

    async def get_latest_ticket(self, current_user: AuthenticatedUser) -> dict[str, Any] | None:
        tickets = await self._owned_tickets(current_user)
        return tickets[0].to_dict() if tickets else None

    async def get_ticket_by_serial_number(
        self,
        current_user: AuthenticatedUser,
        serial_number: int | str,
    ) -> dict[str, Any] | None:
        wanted = str(serial_number).strip()
        for ticket in await self._owned_tickets(current_user):
            if str(ticket.serial_number).strip() == wanted:
                return ticket.to_dict()
        return None

    async def get_ticket_summary(self, current_user: AuthenticatedUser) -> dict[str, int]:
        tickets = await self._owned_tickets(current_user)
        summary = {
            "open": 0,
            "pending": 0,
            "resolved": 0,
            "closed": 0,
            "total": len(tickets),
        }
        for ticket in tickets:
            status = _normalize_status(ticket.status)
            if status in OPEN_STATUSES:
                summary["open"] += 1
            if status in summary:
                summary[status] += 1
        return summary

    async def get_tickets_by_status(
        self,
        current_user: AuthenticatedUser,
        status: str,
    ) -> list[dict[str, Any]]:
        normalized_status = _normalize_status(status.replace("-", " "))
        return [
            ticket.to_dict()
            for ticket in await self._owned_tickets(current_user)
            if _normalize_status(ticket.status) == normalized_status
        ]

    async def _owned_tickets(self, current_user: AuthenticatedUser) -> list[NormalizedItTicket]:
        if not current_user.normalized_identifiers:
            raise ItTicketPermissionError("Verified user identity is unavailable.")

        raw_items = await self._list_items()
        mapping = await self._field_mapping()
        tickets: list[NormalizedItTicket] = []
        for item in raw_items:
            fields = item.get("fields") if isinstance(item, dict) else {}
            if not isinstance(fields, dict):
                continue
            if not _created_by_matches(item, fields, mapping, current_user):
                continue
            tickets.append(_normalize_ticket(item, fields, mapping))

        return sorted(tickets, key=_ticket_sort_key, reverse=True)

    async def _list_items(self) -> list[dict[str, Any]]:
        client = await self._sharepoint_client()
        site_id = await self._resolved_site_id()
        list_id = await self._resolved_list_id(site_id)
        try:
            return await client.get_list_items(site_id, list_id, top=200)
        except GraphClientError as exc:
            status_code = exc.detail.status_code
            if status_code in {401, 403}:
                raise ItTicketPermissionError("Graph permission denied.") from exc
            if status_code == 404:
                raise ItTicketConfigurationError("SharePoint site or list was not found.") from exc
            raise ItTicketTemporaryError("Graph ticket lookup failed.") from exc

    async def _field_mapping(self) -> ItTicketFieldMapping:
        if self._mapping is not None:
            return self._mapping

        if not self.settings.enable_onedesk_it_read:
            raise ItTicketConfigurationError("IT Service Desk read is not enabled.")

        client = await self._sharepoint_client()
        site_id = await self._resolved_site_id()
        list_id = await self._resolved_list_id(site_id)
        columns = await client.get_list_columns(site_id, list_id)
        mapping = get_live_it_ticket_field_mapping(columns)
        missing = mapping.missing_required
        if missing:
            raise ItTicketConfigurationError(
                "Missing IT Service Desk field mapping: " + ", ".join(missing)
            )
        self._mapping = mapping
        return mapping

    async def _resolved_site_id(self) -> str:
        if self._site_id:
            return self._site_id
        configured = self.settings.effective_onedesk_site_id
        if configured:
            self._site_id = configured
            return configured
        site = await (await self._sharepoint_client()).resolve_site(self.settings.onedesk_site_url)
        site_id = str(site.get("id") or "")
        if not site_id:
            raise ItTicketConfigurationError("IT Service Desk site could not be resolved.")
        self._site_id = site_id
        return site_id

    async def _resolved_list_id(self, site_id: str) -> str:
        if self._list_id:
            return self._list_id
        configured = self.settings.effective_it_service_desk_list_id
        if configured:
            self._list_id = configured
            return configured
        list_info = await (await self._sharepoint_client()).get_list_by_title(
            site_id,
            self.settings.effective_it_service_desk_list_title,
        )
        list_id = str((list_info or {}).get("id") or "")
        if not list_id:
            raise ItTicketConfigurationError("IT Service Desk list could not be resolved.")
        self._list_id = list_id
        return list_id

    async def _sharepoint_client(self) -> SharePointClient:
        if self._client is not None:
            return self._client
        if not self.user_access_token:
            raise ItTicketPermissionError("Bearer token is required.")
        graph_token = await OnBehalfOfService().exchange(self.user_access_token)
        self._client = SharePointClient(access_token=graph_token)
        return self._client


def _normalize_ticket(
    item: dict[str, Any],
    fields: dict[str, Any],
    mapping: ItTicketFieldMapping,
) -> NormalizedItTicket:
    return NormalizedItTicket(
        serial_number=_coerce_serial(_field(fields, mapping.ticket_number)),
        title=_optional_text(_field(fields, mapping.title)),
        status=_optional_text(_field(fields, mapping.status)),
        assigned_to=_person_display(_field(fields, mapping.assigned_to)) or "Not assigned",
        priority=_optional_text(_field(fields, mapping.priority)),
        request_type=_optional_text(_field(fields, mapping.request_type)),
        nature_of_complaint=_optional_text(_field(fields, mapping.nature_of_complaint)),
        created_at=_optional_text(_field(fields, mapping.created)) or item.get("createdDateTime"),
        modified_at=_optional_text(_field(fields, mapping.modified)) or item.get("lastModifiedDateTime"),
    )


def _field(fields: dict[str, Any], internal_name: str) -> Any:
    if not internal_name:
        return None
    if internal_name in fields:
        return fields.get(internal_name)
    normalized = internal_name.lower()
    for key, value in fields.items():
        if str(key).lower() == normalized:
            return value
    return None


def _created_by_matches(
    item: dict[str, Any],
    fields: dict[str, Any],
    mapping: ItTicketFieldMapping,
    current_user: AuthenticatedUser,
) -> bool:
    candidates = _person_identifiers(_field(fields, mapping.created_by))
    candidates.update(_person_identifiers(item.get("createdBy")))
    lookup_id = _field(fields, f"{mapping.created_by}LookupId")
    if lookup_id is not None:
        candidates.add(str(lookup_id).strip().lower())
    return bool(candidates & current_user.normalized_identifiers)


def _person_identifiers(value: Any) -> set[str]:
    identifiers: set[str] = set()
    if isinstance(value, dict):
        for key in ("email", "upn", "userPrincipalName", "id", "lookupId"):
            raw = value.get(key)
            if str(raw or "").strip():
                identifiers.add(str(raw).strip().lower())
        for key in ("user", "person", "personOrGroup"):
            nested = value.get(key)
            if isinstance(nested, dict):
                identifiers.update(_person_identifiers(nested))
        display = _person_display(value)
        if display:
            identifiers.add(display.lower())
    elif isinstance(value, list):
        for item in value:
            identifiers.update(_person_identifiers(item))
    elif str(value or "").strip():
        raw = str(value).strip()
        identifiers.add(raw.lower())
        if "@" in raw:
            identifiers.add(raw.split("|")[-1].lower())
    return identifiers


def _person_display(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("displayName", "name", "email", "upn", "userPrincipalName"):
            text = _optional_text(value.get(key))
            if text:
                return text
    if isinstance(value, list):
        names = [_person_display(item) for item in value]
        return ", ".join(name for name in names if name) or None
    return _optional_text(value)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_serial(value: Any) -> int | str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return int(text) if text.isdigit() else text


def _normalize_status(value: str | None) -> str:
    return " ".join(str(value or "").lower().replace("-", " ").split())


def _ticket_sort_key(ticket: NormalizedItTicket) -> datetime:
    for value in (ticket.created_at, ticket.modified_at):
        parsed = _parse_datetime(value)
        if parsed:
            return parsed
    return datetime.min.replace(tzinfo=UTC)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
