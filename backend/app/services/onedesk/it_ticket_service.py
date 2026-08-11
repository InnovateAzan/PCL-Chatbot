from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import logging
from typing import Any

from backend.app.core.config import get_settings
from backend.app.core.logging_config import log_event, mask_email
from backend.app.integrations.microsoft.graph_errors import (
    GraphClientError,
    GraphConfigurationError,
)
from backend.app.integrations.microsoft.obo_service import OnBehalfOfService
from backend.app.integrations.microsoft.sharepoint_client import SharePointClient
from backend.app.security.auth_diagnostics import log_auth_stage, token_format_error
from backend.app.security.entra_auth import AuthenticatedUser
from backend.app.services.onedesk.field_mapping import (
    ItTicketFieldMapping,
    get_live_it_ticket_field_mapping,
)


OPEN_STATUSES = {
    "new",
    "blocked",
    "in progress",
    "reopen",
    "incomplete",
    "pending",
}

CLOSED_STATUSES = {
    "resolved",
    "closed",
}

SUPPORTED_STATUSES = OPEN_STATUSES | CLOSED_STATUSES

logger = logging.getLogger(__name__)


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

        # Cache SharePoint lookup users so the same person is not
        # requested from Graph again for every ticket.
        self._person_lookup_cache: dict[str, str | None] = {}

    async def get_user_tickets(
        self,
        current_user: AuthenticatedUser,
    ) -> list[dict[str, Any]]:
        log_event(
            logger,
            "ticket_lookup_started",
            operation="all",
            user=_safe_user(current_user),
        )

        tickets = await self._owned_tickets(current_user)

        log_event(
            logger,
            "ticket_lookup_completed",
            operation="all",
            result_count=len(tickets),
        )

        return [ticket.to_dict() for ticket in tickets]

    async def get_open_tickets(
        self,
        current_user: AuthenticatedUser,
    ) -> list[dict[str, Any]]:
        log_event(
            logger,
            "ticket_lookup_started",
            operation="open",
            user=_safe_user(current_user),
        )

        tickets = [
            ticket.to_dict()
            for ticket in await self._owned_tickets(current_user)
            if _normalize_status(ticket.status) in OPEN_STATUSES
        ]

        log_event(
            logger,
            "ticket_lookup_completed",
            operation="open",
            result_count=len(tickets),
        )

        return tickets

    async def get_closed_tickets(
        self,
        current_user: AuthenticatedUser,
    ) -> list[dict[str, Any]]:
        log_event(
            logger,
            "ticket_lookup_started",
            operation="closed",
            user=_safe_user(current_user),
        )

        tickets = [
            ticket.to_dict()
            for ticket in await self._owned_tickets(current_user)
            if _normalize_status(ticket.status) in CLOSED_STATUSES
        ]

        log_event(
            logger,
            "ticket_lookup_completed",
            operation="closed",
            result_count=len(tickets),
        )

        return tickets

    async def get_latest_ticket(
        self,
        current_user: AuthenticatedUser,
    ) -> dict[str, Any] | None:
        log_event(
            logger,
            "ticket_lookup_started",
            operation="latest",
            user=_safe_user(current_user),
        )

        tickets = await self._owned_tickets(current_user)

        log_event(
            logger,
            "ticket_lookup_completed",
            operation="latest",
            result_count=1 if tickets else 0,
        )

        return tickets[0].to_dict() if tickets else None

    async def get_ticket_by_serial_number(
        self,
        current_user: AuthenticatedUser,
        serial_number: int | str,
    ) -> dict[str, Any] | None:
        wanted = str(serial_number).strip()

        log_event(
            logger,
            "ticket_lookup_started",
            operation="by_serial",
            serial_number=wanted,
            user=_safe_user(current_user),
        )

        for ticket in await self._owned_tickets(current_user):
            if str(ticket.serial_number).strip() == wanted:
                log_event(
                    logger,
                    "ticket_lookup_completed",
                    operation="by_serial",
                    serial_number=wanted,
                    ticket_found=True,
                    ownership_check="passed",
                    result_count=1,
                )

                return ticket.to_dict()

        log_event(
            logger,
            "ticket_lookup_completed",
            operation="by_serial",
            serial_number=wanted,
            ticket_found=False,
            result_count=0,
        )

        return None

    async def get_ticket_summary(
        self,
        current_user: AuthenticatedUser,
    ) -> dict[str, int]:
        log_event(
            logger,
            "ticket_lookup_started",
            operation="summary",
            user=_safe_user(current_user),
        )

        tickets = await self._owned_tickets(current_user)

        summary = {
            "open": 0,
            "pending": 0,
            "resolved": 0,
            "closed": 0,
            "total": len(tickets),
        }

        for ticket in tickets:
            ticket_status = _normalize_status(ticket.status)

            if ticket_status in OPEN_STATUSES:
                summary["open"] += 1

            if ticket_status in summary:
                summary[ticket_status] += 1

        log_event(
            logger,
            "ticket_lookup_completed",
            operation="summary",
            result_count=len(tickets),
        )

        return summary

    async def get_tickets_by_status(
        self,
        current_user: AuthenticatedUser,
        status: str,
    ) -> list[dict[str, Any]]:
        normalized_status = _normalize_status(
            status.replace("-", " ")
        )

        log_event(
            logger,
            "ticket_lookup_started",
            operation="status",
            status=normalized_status,
            user=_safe_user(current_user),
        )

        tickets = [
            ticket.to_dict()
            for ticket in await self._owned_tickets(current_user)
            if _normalize_status(ticket.status) == normalized_status
        ]

        log_event(
            logger,
            "ticket_lookup_completed",
            operation="status",
            status=normalized_status,
            result_count=len(tickets),
        )

        return tickets

    async def _owned_tickets(
        self,
        current_user: AuthenticatedUser,
    ) -> list[NormalizedItTicket]:
        if not current_user.normalized_identifiers:
            raise ItTicketPermissionError(
                "Verified user identity is unavailable."
            )

        raw_items = await self._list_items()
        mapping = await self._field_mapping()

        client = await self._sharepoint_client()
        site_id = await self._resolved_site_id()

        tickets: list[NormalizedItTicket] = []

        before_count = len(raw_items)

        for item in raw_items:
            fields = (
                item.get("fields")
                if isinstance(item, dict)
                else {}
            )

            if not isinstance(fields, dict):
                continue

            # Security:
            # only tickets created by the authenticated user are exposed.
            if not _created_by_matches(
                item,
                fields,
                mapping,
                current_user,
            ):
                continue

            assigned_to = await self._resolve_assigned_to(
                client=client,
                site_id=site_id,
                fields=fields,
                mapping=mapping,
            )

            ticket = _normalize_ticket(
                item,
                fields,
                mapping,
                assigned_to_override=assigned_to,
            )

            tickets.append(ticket)

        log_event(
            logger,
            "ticket_ownership_filter_completed",
            graph_items_received=before_count,
            ownership_filter_before=before_count,
            ownership_filter_after=len(tickets),
        )

        return sorted(
            tickets,
            key=_ticket_sort_key,
            reverse=True,
        )

    async def _resolve_assigned_to(
        self,
        *,
        client: SharePointClient,
        site_id: str,
        fields: dict[str, Any],
        mapping: ItTicketFieldMapping,
    ) -> str | None:
        """
        Resolve SharePoint Person/Group field.

        Microsoft Graph normally returns:

            Assignedto0LookupId = 22

        rather than:

            Assignedto0 = {"displayName": "User Name"}

        Therefore first use the direct value if available, otherwise resolve
        the SharePoint lookup ID through SharePointClient.
        """

        direct_value = _field(fields, mapping.assigned_to)
        direct_name = _person_display(direct_value)
        if direct_name:
            return direct_name

        lookup_id = _field(fields, f"{mapping.assigned_to}LookupId")

        if lookup_id is None:
            return None

        lookup_key = str(lookup_id).strip()

        if not lookup_key:
            return None

        if lookup_key in self._person_lookup_cache:
            return self._person_lookup_cache[lookup_key]

        try:
            resolved_name = await client.resolve_person_lookup_name(
                site_id,
                lookup_id,
            )
        except GraphClientError as exc:
            log_event(
                logger,
                "ticket_assignee_resolution_failed",
                level=logging.WARNING,
                lookup_id=lookup_key,
                exception_type=type(exc).__name__,
                status_code=getattr(exc.detail, "status_code", None),
            )

            resolved_name = None
        except Exception as exc:
            # Assignee resolution is best effort.
            # A ticket should still be shown if the user name cannot
            # temporarily be resolved.
            log_event(
                logger,
                "ticket_assignee_resolution_failed",
                level=logging.WARNING,
                lookup_id=lookup_key,
                exception_type=type(exc).__name__,
            )

            resolved_name = None

        self._person_lookup_cache[lookup_key] = resolved_name

        log_event(
            logger,
            "ticket_assignee_resolved",
            lookup_id=lookup_key,
            resolved=bool(resolved_name),
        )

        return resolved_name

    async def _list_items(self) -> list[dict[str, Any]]:
        client = await self._sharepoint_client()

        site_id = await self._resolved_site_id()

        list_id = await self._resolved_list_id(site_id)

        try:
            items = await client.get_list_items(
                site_id,
                list_id,
                top=200,
                selected_fields=[
                    "SerialNumber",
                    "Title",
                    "Status",
                    "Assignedto0",
                    "Assignedto0LookupId",
                    "RequestType",
                    "Author",
                    "AuthorLookupId",
                    "Created",
                    "Modified",
                ],
            )

            log_event(
                logger,
                "ticket_graph_items_loaded",
                graph_item_count=len(items),
            )

            return items

        except GraphClientError as exc:
            status_code = exc.detail.status_code

            if status_code in {401, 403}:
                raise ItTicketPermissionError(
                    "graph_permission_denied"
                ) from exc

            if status_code == 404:
                raise ItTicketConfigurationError(
                    "SharePoint site or list was not found."
                ) from exc

            raise ItTicketTemporaryError(
                "Graph ticket lookup failed."
            ) from exc

    async def _field_mapping(self) -> ItTicketFieldMapping:
        if self._mapping is not None:
            return self._mapping

        if not self.settings.enable_onedesk_it_read:
            raise ItTicketConfigurationError(
                "IT Service Desk read is not enabled."
            )

        client = await self._sharepoint_client()

        site_id = await self._resolved_site_id()

        list_id = await self._resolved_list_id(site_id)

        columns = await client.get_list_columns(
            site_id,
            list_id,
        )

        mapping = get_live_it_ticket_field_mapping(columns)

        missing = mapping.missing_required

        if missing:
            log_event(
                logger,
                "ticket_schema_mapping_failed",
                level=logging.ERROR,
                required_fields_missing=missing,
            )

            raise ItTicketConfigurationError(
                "Missing IT Service Desk field mapping: "
                + ", ".join(missing)
            )

        log_event(
            logger,
            "ticket_schema_mapping_loaded",
            mapped_fields=[
                field
                for field in [
                    mapping.ticket_number,
                    mapping.title,
                    mapping.status,
                    mapping.assigned_to,
                    mapping.created_by,
                    mapping.request_type,
                    mapping.nature_of_complaint,
                    mapping.created,
                    mapping.modified,
                ]
                if field
            ],
        )

        self._mapping = mapping

        return mapping

    async def _resolved_site_id(self) -> str:
        if self._site_id:
            return self._site_id

        configured = self.settings.effective_onedesk_site_id

        if configured:
            self._site_id = configured

            log_event(
                logger,
                "ticket_site_resolved",
                configured=True,
                site_resolved=True,
            )

            return configured

        log_event(
            logger,
            "ticket_site_resolution_started",
            site_url_configured=bool(
                self.settings.onedesk_site_url
            ),
        )

        site = await (
            await self._sharepoint_client()
        ).resolve_site(
            self.settings.onedesk_site_url
        )

        site_id = str(
            site.get("id") or ""
        ).strip()

        if not site_id:
            log_event(
                logger,
                "ticket_site_resolution_failed",
                level=logging.ERROR,
                site_resolved=False,
            )

            raise ItTicketConfigurationError(
                "IT Service Desk site could not be resolved."
            )

        self._site_id = site_id

        log_event(
            logger,
            "ticket_site_resolved",
            configured=False,
            site_resolved=True,
        )

        return site_id

    async def _resolved_list_id(
        self,
        site_id: str,
    ) -> str:
        if self._list_id:
            return self._list_id

        configured = (
            self.settings.effective_it_service_desk_list_id
        )

        if configured:
            self._list_id = configured

            log_event(
                logger,
                "ticket_list_resolved",
                configured=True,
                list_resolved=True,
            )

            return configured

        log_event(
            logger,
            "ticket_list_resolution_started",
            list_title=(
                self.settings.effective_it_service_desk_list_title
            ),
        )

        list_info = await (
            await self._sharepoint_client()
        ).get_list_by_title(
            site_id,
            self.settings.effective_it_service_desk_list_title,
        )

        list_id = str(
            (list_info or {}).get("id") or ""
        ).strip()

        if not list_id:
            log_event(
                logger,
                "ticket_list_resolution_failed",
                level=logging.ERROR,
                list_resolved=False,
            )

            raise ItTicketConfigurationError(
                "IT Service Desk list could not be resolved."
            )

        self._list_id = list_id

        log_event(
            logger,
            "ticket_list_resolved",
            configured=False,
            list_resolved=True,
        )

        return list_id

    async def _sharepoint_client(self) -> SharePointClient:
        if self._client is not None:
            return self._client

        format_error = token_format_error(
            self.user_access_token
        )

        if format_error:
            log_auth_stage(
                "ticket_sharepoint_client",
                token=self.user_access_token,
                result="failed",
                extra={
                    "api_token_validation_result": format_error,
                },
            )

            raise ItTicketPermissionError(format_error)

        graph_token = await OnBehalfOfService().exchange(
            self.user_access_token
        )

        self._client = SharePointClient(
            access_token=graph_token
        )

        return self._client


def _safe_user(
    current_user: AuthenticatedUser,
) -> dict[str, str | None]:
    return {
        "oid": current_user.oid,
        "email": mask_email(current_user.email),
    }


def _normalize_ticket(
    item: dict[str, Any],
    fields: dict[str, Any],
    mapping: ItTicketFieldMapping,
    *,
    assigned_to_override: str | None = None,
) -> NormalizedItTicket:
    assigned_to = (
        assigned_to_override
        or _person_display(
            _field(
                fields,
                mapping.assigned_to,
            )
        )
        or "Not assigned"
    )

    return NormalizedItTicket(
        serial_number=_coerce_serial(
            _field(
                fields,
                mapping.ticket_number,
            )
        ),
        title=_optional_text(
            _field(
                fields,
                mapping.title,
            )
        ),
        status=_optional_text(
            _field(
                fields,
                mapping.status,
            )
        ),
        assigned_to=assigned_to,

        # Kept in backend model for compatibility.
        # You can hide Priority from ticket_service.py formatter.
        priority=_optional_text(
            _field(
                fields,
                mapping.priority,
            )
        ),

        request_type=_optional_text(
            _field(
                fields,
                mapping.request_type,
            )
        ),
        nature_of_complaint=_optional_text(
            _field(
                fields,
                mapping.nature_of_complaint,
            )
        ),
        created_at=_optional_text(
            _field(
                fields,
                mapping.created,
            )
        )
        or item.get("createdDateTime"),
        modified_at=_optional_text(
            _field(
                fields,
                mapping.modified,
            )
        )
        or item.get("lastModifiedDateTime"),
    )


def _field(
    fields: dict[str, Any],
    internal_name: str,
) -> Any:
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
    candidates = _person_identifiers(
        _field(
            fields,
            mapping.created_by,
        )
    )

    candidates.update(
        _person_identifiers(
            item.get("createdBy")
        )
    )

    lookup_id = _field(
        fields,
        f"{mapping.created_by}LookupId",
    )

    if lookup_id is not None:
        candidates.add(
            str(lookup_id).strip().lower()
        )

    return bool(
        candidates
        & current_user.normalized_identifiers
    )


def _person_identifiers(
    value: Any,
) -> set[str]:
    identifiers: set[str] = set()

    if isinstance(value, dict):
        for key in (
            "email",
            "upn",
            "userPrincipalName",
            "id",
            "lookupId",
        ):
            raw = value.get(key)

            if str(raw or "").strip():
                identifiers.add(
                    str(raw).strip().lower()
                )

        for key in (
            "user",
            "person",
            "personOrGroup",
        ):
            nested = value.get(key)

            if isinstance(nested, dict):
                identifiers.update(
                    _person_identifiers(nested)
                )

        display = _person_display(value)

        if display:
            identifiers.add(display.lower())

    elif isinstance(value, list):
        for item in value:
            identifiers.update(
                _person_identifiers(item)
            )

    elif str(value or "").strip():
        raw = str(value).strip()

        identifiers.add(raw.lower())

        if "@" in raw:
            identifiers.add(
                raw.split("|")[-1].lower()
            )

    return identifiers


def _person_display(
    value: Any,
) -> str | None:
    if isinstance(value, dict):
        for key in (
            "displayName",
            "name",
            "Title",
            "email",
            "EMail",
            "Email",
            "upn",
            "userPrincipalName",
        ):
            text = _optional_text(
                value.get(key)
            )

            if text:
                return text

    if isinstance(value, list):
        names = [
            _person_display(item)
            for item in value
        ]

        return (
            ", ".join(
                name
                for name in names
                if name
            )
            or None
        )

    return _optional_text(value)


def _optional_text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    text = str(value).strip()

    return text or None


def _coerce_serial(
    value: Any,
) -> int | str:
    text = str(value or "").strip()

    if text.endswith(".0"):
        text = text[:-2]

    return (
        int(text)
        if text.isdigit()
        else text
    )


def _normalize_status(
    value: str | None,
) -> str:
    return " ".join(
        str(value or "")
        .lower()
        .replace("-", " ")
        .split()
    )


def _ticket_sort_key(
    ticket: NormalizedItTicket,
) -> datetime:
    for value in (
        ticket.created_at,
        ticket.modified_at,
    ):
        parsed = _parse_datetime(value)

        if parsed:
            return parsed

    return datetime.min.replace(tzinfo=UTC)


def _parse_datetime(
    value: str | None,
) -> datetime | None:
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError:
        return None
