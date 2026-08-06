from __future__ import annotations

from backend.app.core.config import get_settings
from backend.app.integrations.microsoft.graph_errors import GraphConfigurationError
from backend.app.models.schemas import ChatResponse
from backend.app.security.current_user import resolve_current_user_from_authorization
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


class OneDeskService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.intent_service = OneDeskIntentService()
        self.client = GraphOneDeskClient()
        self.formatter = OneDeskResponseFormatter()

    def should_handle(self, message: str) -> bool:
        intent = self.intent_service.detect(message)
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
    ) -> ChatResponse:
        intent = self.intent_service.detect(message)
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
            )

        if not self.settings.enable_onedesk_integration:
            return ChatResponse(
                answer=(
                    "OneDesk live-data lookup is not enabled yet. "
                    "Please set ENABLE_ONEDESK_INTEGRATION=true after configuring SharePoint list settings."
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
            list_id=getattr(self.settings, f"{prefix}list_id", ""),
            list_title=getattr(self.settings, f"{prefix}list_title", ""),
            user_email_field=getattr(self.settings, f"{prefix}user_email_field", ""),
            request_number_field=getattr(self.settings, f"{prefix}ticket_number_field", ""),
            status_field=getattr(self.settings, f"{prefix}status_field", ""),
            assigned_to_field=getattr(self.settings, f"{prefix}assigned_to_field", ""),
            updated_field=getattr(self.settings, f"{prefix}updated_field", ""),
            latest_update_field=getattr(self.settings, f"{prefix}latest_update_field", ""),
        )

    async def _answer_it_ticket_intent(
        self,
        *,
        message: str,
        access_token: str | None,
    ) -> ChatResponse:
        intent = self.intent_service.detect(message)
        try:
            current_user = resolve_current_user_from_authorization(
                f"Bearer {access_token}" if access_token else None
            )
            service = ItTicketService(access_token=access_token)
            if intent.intent_type == "IT_TICKET_OPEN":
                tickets = await service.get_open_tickets(current_user)
                answer = _format_ticket_list("Your open tickets:", tickets)
            elif intent.intent_type == "IT_TICKET_CLOSED":
                tickets = await service.get_closed_tickets(current_user)
                answer = _format_ticket_list("Your closed tickets:", tickets)
            elif intent.intent_type == "IT_TICKET_LATEST":
                ticket = await service.get_latest_ticket(current_user)
                answer = _format_latest_ticket(ticket)
            elif intent.intent_type == "IT_TICKET_SUMMARY":
                answer = _format_summary(await service.get_ticket_summary(current_user))
            elif intent.intent_type == "IT_TICKET_STATUS_COUNT" and intent.status:
                tickets = await service.get_tickets_by_status(current_user, intent.status)
                answer = f"You have {len(tickets)} {intent.status} ticket{'s' if len(tickets) != 1 else ''}."
            elif intent.intent_type in {"IT_TICKET_SERIAL", "IT_TICKET_STATUS"} and intent.request_number:
                ticket = await service.get_ticket_by_serial_number(
                    current_user,
                    intent.request_number,
                )
                answer = _format_specific_ticket(ticket, intent.request_number)
            elif intent.intent_type == "IT_TICKET_STATUS_LIST" and intent.status:
                tickets = await service.get_tickets_by_status(current_user, intent.status)
                answer = _format_ticket_list(f"Your {intent.status} tickets:", tickets)
            else:
                tickets = await service.get_user_tickets(current_user)
                answer = _format_ticket_list("Your IT Service Desk tickets:", tickets)
        except (PermissionError, ItTicketPermissionError):
            answer = "Your Microsoft session is invalid or expired."
            fallback = True
        except (GraphConfigurationError, ItTicketConfigurationError):
            answer = "The IT Service Desk integration is not fully configured."
            fallback = True
        except ItTicketTemporaryError:
            answer = "Live ticket information is temporarily unavailable."
            fallback = True

        return ChatResponse(
            answer=answer,
            sources=[],
            fallback=locals().get("fallback", False),
            provider="onedesk-it-live",
            notice="Data Source: IT Service Desk",
            responseSource="ONEDESK",
        )


def _format_ticket_list(title: str, tickets: list[dict]) -> str:
    if not tickets:
        return "No IT Service Desk tickets were found for your account."
    blocks = [title]
    for ticket in tickets[:10]:
        lines = [
            f"• Ticket #{ticket.get('serial_number') or 'Not available'}",
            f"  Title: {_display(ticket.get('title'))}",
            f"  Status: {_display(ticket.get('status'))}",
            f"  Assigned To: {_display(ticket.get('assigned_to'), 'Not assigned')}",
        ]
        if ticket.get("request_type"):
            lines.append(f"  Request Type: {ticket['request_type']}")
        if ticket.get("created_at"):
            lines.append(f"  Created: {_format_date(ticket['created_at'])}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _format_latest_ticket(ticket: dict | None) -> str:
    if not ticket:
        return "No IT Service Desk tickets were found for your account."
    return (
        f"Your latest ticket is #{ticket.get('serial_number')}.\n\n"
        f"Title: {_display(ticket.get('title'))}\n"
        f"Status: {_display(ticket.get('status'))}\n"
        f"Assigned To: {_display(ticket.get('assigned_to'), 'Not assigned')}\n"
        f"Created: {_format_date(ticket.get('created_at'))}"
    )


def _format_summary(summary: dict[str, int]) -> str:
    return (
        "Your ticket summary:\n\n"
        f"• Open: {summary.get('open', 0)}\n"
        f"• Pending: {summary.get('pending', 0)}\n"
        f"• Resolved: {summary.get('resolved', 0)}\n"
        f"• Closed: {summary.get('closed', 0)}\n"
        f"• Total: {summary.get('total', 0)}"
    )


def _format_specific_ticket(ticket: dict | None, serial_number: str) -> str:
    if not ticket:
        return f"Ticket #{serial_number} was not found in your account."
    return (
        f"Ticket #{ticket.get('serial_number')}\n\n"
        f"Title: {_display(ticket.get('title'))}\n"
        f"Status: {_display(ticket.get('status'))}\n"
        f"Assigned To: {_display(ticket.get('assigned_to'), 'Not assigned')}\n"
        f"Priority: {_display(ticket.get('priority'))}\n"
        f"Request Type: {_display(ticket.get('request_type'))}\n"
        f"Created: {_format_date(ticket.get('created_at'))}\n"
        f"Last Modified: {_format_date(ticket.get('modified_at'))}"
    )


def _display(value: object, default: str = "Not available") -> str:
    text = str(value or "").strip()
    return text or default


def _format_date(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "Not available"
    try:
        from datetime import datetime

        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return f"{parsed.day} {parsed.strftime('%B %Y')}"
    except ValueError:
        return text
