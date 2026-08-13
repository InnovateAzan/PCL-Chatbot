from __future__ import annotations

import logging

from backend.app.core.config import get_settings
from backend.app.core.logging_config import log_event
from backend.app.integrations.microsoft.graph_errors import GraphConfigurationError
from backend.app.models.schemas import ChatResponse
from backend.app.security.auth_diagnostics import public_auth_message
from backend.app.security.current_user import resolve_current_user_from_authorization
from backend.app.security.entra_auth import AuthenticationError
from backend.app.services.onedesk.base_client import OneDeskListConfig
from backend.app.services.onedesk.graph_client import GraphOneDeskClient
from backend.app.services.onedesk.it_ticket_service import (
    ItTicketConfigurationError,
    ItTicketPermissionError,
    ItTicketService,
    ItTicketTemporaryError,
)
from backend.app.services.onedesk.intent_service import OneDeskIntentService
from backend.app.services.onedesk.response_formatter import OneDeskResponseFormatter


logger = logging.getLogger(__name__)


class OneDeskService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.intent_service = OneDeskIntentService()
        self.client = GraphOneDeskClient()
        self.formatter = OneDeskResponseFormatter()
        self._session_ticket_contexts: dict[str, str] = {}

    def get_ticket_context(
        self,
        session_key: str | None,
    ) -> str | None:
        if not session_key:
            return None
        return self._session_ticket_contexts.get(session_key)

    def should_handle(
        self,
        message: str,
        *,
        context_request_number: str | None = None,
        session_key: str | None = None,
    ) -> bool:
        if not context_request_number and session_key:
            context_request_number = self.get_ticket_context(session_key)

        intent = self.intent_service.detect(
            message,
            context_request_number=context_request_number,
        )

        log_event(
            logger,
            "ticket_intent_detected",
            intent_type=intent.intent_type,
            module=intent.module,
            request_number=intent.request_number,
        )

        return intent.module is not None and intent.intent_type not in {
            "POLICY_QUESTION",
            "GENERAL_QUESTION",
            "GREETING",
        }

    async def answer(
        self,
        *,
        message: str,
        user_email: str,
        access_token: str | None = None,
        context_request_number: str | None = None,
        session_key: str | None = None,
    ) -> ChatResponse:
        if not context_request_number and session_key:
            context_request_number = self.get_ticket_context(session_key)

        intent = self.intent_service.detect(
            message,
            context_request_number=context_request_number,
        )

        if not intent.module:
            return ChatResponse(
                answer="This does not look like a OneDesk live-data request.",
                fallback=True,
                provider="onedesk-rules",
            )

        if intent.module == "it" and self.settings.enable_onedesk_it_read:
            return await self._answer_it_ticket_intent(
                message=message,
                access_token=access_token,
                context_request_number=context_request_number,
                session_key=session_key,
            )

        if not self.settings.enable_onedesk_integration:
            return ChatResponse(
                answer=(
                    "OneDesk live-data lookup is not enabled yet. "
                    "Please set ENABLE_ONEDESK_INTEGRATION=true after "
                    "configuring SharePoint list settings."
                ),
                fallback=True,
                provider="onedesk-disabled",
                responseSource="ONEDESK",
            )

        config = self._config_for(intent.module)

        if not config or not config.is_configured:
            return ChatResponse(
                answer=f"OneDesk {intent.module} configuration is incomplete.",
                fallback=True,
                provider="onedesk-config",
                responseSource="ONEDESK",
            )

        records = await self.client.query_user_records(
            config=config,
            user_email=user_email,
            request_number=intent.request_number,
            access_token=access_token,
        )

        return ChatResponse(
            answer=self.formatter.format_records(
                config=config,
                records=records,
                request_number=intent.request_number,
            ),
            fallback=False,
            provider="onedesk-live",
            responseSource="ONEDESK",
        )

    def _config_for(self, module: str) -> OneDeskListConfig | None:
        prefix = f"onedesk_{module}_"

        return OneDeskListConfig(
            module=module,
            list_id=getattr(
                self.settings,
                f"{prefix}list_id",
                "",
            ),
            list_title=getattr(
                self.settings,
                f"{prefix}list_title",
                "",
            ),
            user_email_field=getattr(
                self.settings,
                f"{prefix}user_email_field",
                "",
            ),
            request_number_field=getattr(
                self.settings,
                f"{prefix}ticket_number_field",
                "",
            ),
            status_field=getattr(
                self.settings,
                f"{prefix}status_field",
                "",
            ),
            assigned_to_field=getattr(
                self.settings,
                f"{prefix}assigned_to_field",
                "",
            ),
            updated_field=getattr(
                self.settings,
                f"{prefix}updated_field",
                "",
            ),
            latest_update_field=getattr(
                self.settings,
                f"{prefix}latest_update_field",
                "",
            ),
        )

    async def _answer_it_ticket_intent(
        self,
        *,
        message: str,
        access_token: str | None,
        context_request_number: str | None = None,
        session_key: str | None = None,
    ) -> ChatResponse:
        if not context_request_number and session_key:
            context_request_number = self.get_ticket_context(session_key)

        intent = self.intent_service.detect(
            message,
            context_request_number=context_request_number,
        )

        log_event(
            logger,
            "onedesk_request_received",
            intent_type=intent.intent_type,
            module=intent.module,
            request_number=intent.request_number,
        )

        try:
            current_user = resolve_current_user_from_authorization(
                f"Bearer {access_token}" if access_token else None
            )

            service = ItTicketService(
                access_token=access_token
            )

            if intent.intent_type == "IT_TICKET_OPEN":
                tickets = await service.get_open_tickets(
                    current_user
                )

                answer = _format_ticket_list(
                    "Your open tickets",
                    tickets,
                )
                self._remember_ticket_context(session_key, tickets)

            elif intent.intent_type == "IT_TICKET_CLOSED":
                tickets = await service.get_closed_tickets(
                    current_user
                )

                answer = _format_ticket_list(
                    "Your closed tickets",
                    tickets,
                )
                self._remember_ticket_context(session_key, tickets)

            elif intent.intent_type == "IT_TICKET_LATEST":
                ticket = await service.get_latest_ticket(
                    current_user
                )

                answer = _format_latest_ticket(
                    ticket
                )
                self._remember_ticket_context(session_key, [ticket] if ticket else [])

            elif intent.intent_type == "IT_TICKET_SUMMARY":
                summary = await service.get_ticket_summary(
                    current_user
                )

                answer = _format_summary(
                    summary
                )

            elif (
                intent.intent_type == "IT_TICKET_STATUS_COUNT"
                and intent.status
            ):
                tickets = await service.get_tickets_by_status(
                    current_user,
                    intent.status,
                )

                answer = (
                    f"You have {len(tickets)} "
                    f"{intent.status} "
                    f"ticket{'s' if len(tickets) != 1 else ''}."
                )
                self._remember_ticket_context(session_key, tickets)

            elif (
                intent.intent_type == "IT_TICKET_ASSIGNEE"
                and intent.request_number
            ):
                ticket = await service.get_ticket_by_serial_number(
                    current_user,
                    intent.request_number,
                )

                answer = _format_ticket_assignee(
                    ticket,
                    intent.request_number,
                )
                self._remember_ticket_context(session_key, [ticket] if ticket else [])

            elif (
                intent.intent_type == "IT_TICKET_REQUEST_TYPE"
                and intent.request_number
            ):
                ticket = await service.get_ticket_by_serial_number(
                    current_user,
                    intent.request_number,
                )

                answer = _format_ticket_request_type(
                    ticket,
                    intent.request_number,
                )
                self._remember_ticket_context(session_key, [ticket] if ticket else [])

            elif (
                intent.intent_type == "IT_TICKET_CREATED"
                and intent.request_number
            ):
                ticket = await service.get_ticket_by_serial_number(
                    current_user,
                    intent.request_number,
                )

                answer = _format_ticket_created(
                    ticket,
                    intent.request_number,
                )
                self._remember_ticket_context(session_key, [ticket] if ticket else [])

            elif (
                intent.intent_type == "IT_TICKET_MODIFIED"
                and intent.request_number
            ):
                ticket = await service.get_ticket_by_serial_number(
                    current_user,
                    intent.request_number,
                )

                answer = _format_ticket_modified(
                    ticket,
                    intent.request_number,
                )
                self._remember_ticket_context(session_key, [ticket] if ticket else [])

            elif (
                intent.intent_type == "IT_TICKET_STATUS"
                and intent.request_number
            ):
                ticket = await service.get_ticket_by_serial_number(
                    current_user,
                    intent.request_number,
                )

                answer = _format_ticket_status(
                    ticket,
                    intent.request_number,
                )
                self._remember_ticket_context(session_key, [ticket] if ticket else [])

            elif (
                intent.intent_type == "IT_TICKET_DETAILS"
                and intent.request_number
            ):
                ticket = await service.get_ticket_by_serial_number(
                    current_user,
                    intent.request_number,
                )

                answer = _format_specific_ticket(
                    ticket,
                    intent.request_number,
                )
                self._remember_ticket_context(session_key, [ticket] if ticket else [])
            elif (
                intent.intent_type == "IT_TICKET_DETAILS_LOOKUP"
                and intent.request_query
            ):
                tickets = await service.find_tickets_by_query(
                    current_user,
                    intent.request_query,
                )
                if len(tickets) == 1:
                    ticket = tickets[0]
                    answer = _format_specific_ticket(
                        ticket,
                        str(ticket.get("serial_number") or intent.request_query),
                    )
                    self._remember_ticket_context(session_key, [ticket])
                elif len(tickets) > 1:
                    answer = "I found multiple matching tickets. Please be more specific."
                    self._remember_ticket_context(session_key, tickets)
                else:
                    answer = "I couldn't find a matching ticket in the tickets available to your account."
            elif (
                intent.intent_type == "IT_TICKET_STATUS_LOOKUP"
                and intent.request_query
            ):
                tickets = await service.find_tickets_by_query(
                    current_user,
                    intent.request_query,
                )
                if len(tickets) == 1:
                    ticket = tickets[0]
                    answer = _format_ticket_status(
                        ticket,
                        str(ticket.get("serial_number") or intent.request_query),
                    )
                    self._remember_ticket_context(session_key, [ticket])
                elif len(tickets) > 1:
                    answer = "I found multiple matching tickets. Please be more specific."
                    self._remember_ticket_context(session_key, tickets)
                else:
                    answer = "I couldn't find a matching ticket in the tickets available to your account."
            elif (
                intent.intent_type == "IT_TICKET_ASSIGNEE_LOOKUP"
                and intent.request_query
            ):
                tickets = await service.find_tickets_by_query(
                    current_user,
                    intent.request_query,
                )
                if len(tickets) == 1:
                    ticket = tickets[0]
                    answer = _format_ticket_assignee(
                        ticket,
                        str(ticket.get("serial_number") or intent.request_query),
                    )
                    self._remember_ticket_context(session_key, [ticket])
                elif len(tickets) > 1:
                    answer = "I found multiple matching tickets. Please be more specific."
                    self._remember_ticket_context(session_key, tickets)
                else:
                    answer = "I couldn't find a matching ticket in the tickets available to your account."
            elif (
                intent.intent_type == "IT_TICKET_REQUEST_TYPE_LOOKUP"
                and intent.request_query
            ):
                tickets = await service.find_tickets_by_query(
                    current_user,
                    intent.request_query,
                )
                if len(tickets) == 1:
                    ticket = tickets[0]
                    answer = _format_ticket_request_type(
                        ticket,
                        str(ticket.get("serial_number") or intent.request_query),
                    )
                    self._remember_ticket_context(session_key, [ticket])
                elif len(tickets) > 1:
                    answer = "I found multiple matching tickets. Please be more specific."
                    self._remember_ticket_context(session_key, tickets)
                else:
                    answer = "I couldn't find a matching ticket in the tickets available to your account."
            elif (
                intent.intent_type == "IT_TICKET_CREATED_LOOKUP"
                and intent.request_query
            ):
                tickets = await service.find_tickets_by_query(
                    current_user,
                    intent.request_query,
                )
                if len(tickets) == 1:
                    ticket = tickets[0]
                    answer = _format_ticket_created(
                        ticket,
                        str(ticket.get("serial_number") or intent.request_query),
                    )
                    self._remember_ticket_context(session_key, [ticket])
                elif len(tickets) > 1:
                    answer = "I found multiple matching tickets. Please be more specific."
                    self._remember_ticket_context(session_key, tickets)
                else:
                    answer = "I couldn't find a matching ticket in the tickets available to your account."
            elif (
                intent.intent_type == "IT_TICKET_MODIFIED_LOOKUP"
                and intent.request_query
            ):
                tickets = await service.find_tickets_by_query(
                    current_user,
                    intent.request_query,
                )
                if len(tickets) == 1:
                    ticket = tickets[0]
                    answer = _format_ticket_modified(
                        ticket,
                        str(ticket.get("serial_number") or intent.request_query),
                    )
                    self._remember_ticket_context(session_key, [ticket])
                elif len(tickets) > 1:
                    answer = "I found multiple matching tickets. Please be more specific."
                    self._remember_ticket_context(session_key, tickets)
                else:
                    answer = "I couldn't find a matching ticket in the tickets available to your account."

            elif (
                intent.intent_type == "IT_TICKET_STATUS_LIST"
                and intent.status
            ):
                tickets = await service.get_tickets_by_status(
                    current_user,
                    intent.status,
                )

                answer = _format_ticket_list(
                    f"Your {intent.status} tickets",
                    tickets,
                )
                self._remember_ticket_context(session_key, tickets)

            elif intent.intent_type == "IT_TICKET_ASSIGNED_TO_ME":
                tickets = await service.get_assigned_to_me_tickets(
                    current_user,
                    user_email=current_user.email,
                )

                answer = _format_compact_ticket_list(
                    "Tickets assigned to you",
                    tickets,
                )
                self._remember_ticket_context(session_key, tickets)

            elif intent.intent_type == "IT_TICKET_UNASSIGNED":
                tickets = await service.get_unassigned_tickets(
                    current_user,
                )

                answer = _format_compact_ticket_list(
                    "Unassigned tickets",
                    tickets,
                )
                self._remember_ticket_context(session_key, tickets)

            else:
                tickets = await service.get_user_tickets(
                    current_user
                )

                answer = _format_ticket_list(
                    "Your IT Service Desk tickets",
                    tickets,
                )

        except AuthenticationError as exc:
            answer = public_auth_message(
                getattr(
                    exc,
                    "code",
                    "validation_failed",
                )
            )
            fallback = True

        except PermissionError:
            answer = public_auth_message(
                "token_missing"
            )
            fallback = True

        except ItTicketPermissionError as exc:
            answer = public_auth_message(
                str(exc)
                or "graph_permission_denied"
            )
            fallback = True

        except GraphConfigurationError as exc:
            answer = _format_graph_configuration_error(
                exc
            )
            fallback = True

        except ItTicketConfigurationError as exc:
            answer = (
                "IT Service Desk configuration error: "
                f"{str(exc)}"
            )
            fallback = True

        except ItTicketTemporaryError:
            answer = (
                "Live ticket information is temporarily unavailable."
            )
            fallback = True

        return ChatResponse(
            answer=answer,
            sources=[],
            fallback=locals().get(
                "fallback",
                False,
            ),
            provider="onedesk-it-live",

            # Keep Data Source only here.
            # Do not repeat it inside formatter text.
            notice="Data Source: IT Service Desk",

            responseSource="ONEDESK",
        )

    def _remember_ticket_context(
        self,
        session_key: str | None,
        tickets: list[dict],
    ) -> None:
        if not session_key or not tickets:
            return

        serial_number = tickets[0].get("serial_number")
        if serial_number is None:
            return

        self._session_ticket_contexts[session_key] = str(serial_number)


def _format_graph_configuration_error(
    error: GraphConfigurationError,
) -> str:
    code = getattr(
        error,
        "code",
        None,
    )

    if code:
        return (
            f"{public_auth_message('obo_failed')} "
            f"Safe Microsoft error: {code}."
        )

    return (
        "The IT Service Desk integration is not fully configured."
    )


def _format_ticket_list(
    title: str,
    tickets: list[dict],
) -> str:
    if not tickets:
        return (
            "No IT Service Desk tickets were found "
            "for your account."
        )

    blocks = [title]

    for ticket in tickets[:10]:
        serial_number = (
            ticket.get("serial_number")
            or "Not available"
        )

        status = _display(
            ticket.get("status")
        )

        lines = [
            f"Ticket #{serial_number} — {status}",
            _display(
                ticket.get("title")
            ),
            (
                "Assigned To: "
                f"{_display(ticket.get('assigned_to'), 'Not assigned')}"
            ),
        ]

        if ticket.get("request_type"):
            lines.append(
                "Request Type: "
                f"{_display(ticket.get('request_type'))}"
            )

        if ticket.get("created_at"):
            lines.append(
                "Created: "
                f"{_format_date(ticket.get('created_at'))}"
            )

        blocks.append(
            "\n".join(lines)
        )

    return "\n\n".join(
        blocks
    )


def _format_latest_ticket(
    ticket: dict | None,
) -> str:
    if not ticket:
        return (
            "No IT Service Desk tickets were found "
            "for your account."
        )

    serial_number = _display(
        ticket.get("serial_number")
    )

    status = _display(
        ticket.get("status")
    )

    lines = [
        f"Ticket #{serial_number} — {status}",
        "",
        f"Title: {_display(ticket.get('title'))}",
        (
            "Assigned To: "
            f"{_display(ticket.get('assigned_to'), 'Not assigned')}"
        ),
        (
            "Request Type: "
            f"{_display(ticket.get('request_type'))}"
        ),
        (
            "Created: "
            f"{_format_date(ticket.get('created_at'))}"
        ),
        (
            "Last Updated: "
            f"{_format_date(ticket.get('modified_at'))}"
        ),
    ]

    return "\n".join(
        lines
    )


def _format_summary(
    summary: dict[str, int],
) -> str:
    return (
        "Your ticket summary:\n\n"
        f"Open: {summary.get('open', 0)}\n"
        f"Pending: {summary.get('pending', 0)}\n"
        f"Resolved: {summary.get('resolved', 0)}\n"
        f"Closed: {summary.get('closed', 0)}\n"
        f"Total: {summary.get('total', 0)}"
    )


def _format_specific_ticket(
    ticket: dict | None,
    serial_number: str,
) -> str:
    if not ticket:
        return (
            f"Ticket #{serial_number} was not found "
            "in your account."
        )

    serial = _display(
        ticket.get("serial_number"),
        serial_number,
    )

    status = _display(
        ticket.get("status")
    )

    headline = (
        f"Ticket #{serial} — {status}"
        if status
        else f"Ticket #{serial}"
    )

    lines = [
        headline,
        "",
        f"Title: {_display(ticket.get('title'))}",
        f"Status: {status}",
        (
            "Assigned To: "
            f"{_display(ticket.get('assigned_to'), 'Not assigned')}"
        ),
        (
            "Request Type: "
            f"{_display(ticket.get('request_type'))}"
        ),
        (
            "Created: "
            f"{_format_date(ticket.get('created_at'))}"
        ),
        (
            "Last Updated: "
            f"{_format_date(ticket.get('modified_at'))}"
        ),
    ]

    return "\n".join(
        lines
    )


def _format_ticket_assignee(
    ticket: dict | None,
    serial_number: str,
) -> str:
    if not ticket:
        return (
            f"Ticket #{serial_number} was not found "
            "in your account."
        )

    serial = _display(
        ticket.get("serial_number"),
        serial_number,
    )

    lines = [
        f"Ticket #{serial}",
        "",
        (
            "Assigned To: "
            f"{_display(ticket.get('assigned_to'), 'Not assigned')}"
        ),
    ]

    return "\n".join(
        lines
    )


def _format_ticket_status(
    ticket: dict | None,
    serial_number: str,
) -> str:
    if not ticket:
        return (
            f"Ticket #{serial_number} was not found "
            "in your account."
        )

    serial = _display(
        ticket.get("serial_number"),
        serial_number,
    )

    lines = [
        f"Ticket #{serial}",
        "",
        (
            "Status: "
            f"{_display(ticket.get('status'))}"
        ),
    ]

    return "\n".join(
        lines
    )


def _format_ticket_request_type(
    ticket: dict | None,
    serial_number: str,
) -> str:
    if not ticket:
        return (
            f"Ticket #{serial_number} was not found "
            "in your account."
        )

    serial = _display(
        ticket.get("serial_number"),
        serial_number,
    )

    lines = [
        f"Ticket #{serial}",
        "",
        (
            "Request Type: "
            f"{_display(ticket.get('request_type'))}"
        ),
    ]

    return "\n".join(
        lines
    )


def _format_compact_ticket_list(
    title: str,
    tickets: list[dict],
) -> str:
    if not tickets:
        return (
            "No IT Service Desk tickets were found "
            "for your account."
        )

    blocks = [title]

    for ticket in tickets[:10]:
        serial_number = (
            ticket.get("serial_number")
            or "Not available"
        )
        status = _display(ticket.get("status"))
        lines = [
            f"Ticket #{serial_number} â€” {status}",
        ]

        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


def _format_ticket_created(
    ticket: dict | None,
    serial_number: str,
) -> str:
    if not ticket:
        return (
            f"Ticket #{serial_number} was not found "
            "in your account."
        )

    serial = _display(
        ticket.get("serial_number"),
        serial_number,
    )

    lines = [
        f"Ticket #{serial}",
        "",
        f"Created: {_format_date(ticket.get('created_at'))}",
    ]

    return "\n".join(lines)


def _format_ticket_modified(
    ticket: dict | None,
    serial_number: str,
) -> str:
    if not ticket:
        return (
            f"Ticket #{serial_number} was not found "
            "in your account."
        )

    serial = _display(
        ticket.get("serial_number"),
        serial_number,
    )

    lines = [
        f"Ticket #{serial}",
        "",
        f"Last Updated: {_format_date(ticket.get('modified_at'))}",
    ]

    return "\n".join(lines)


def _format_ticket_link(
    value: object,
) -> str:
    return ""


def _display(
    value: object,
    default: str = "Not available",
) -> str:
    text = str(
        value or ""
    ).strip()

    return text or default


def _format_date(
    value: object,
) -> str:
    text = str(
        value or ""
    ).strip()

    if not text:
        return "Not available"

    try:
        from datetime import datetime

        parsed = datetime.fromisoformat(
            text.replace(
                "Z",
                "+00:00",
            )
        )

        return (
            f"{parsed.day} "
            f"{parsed.strftime('%B %Y')}"
        )

    except ValueError:
        return text
