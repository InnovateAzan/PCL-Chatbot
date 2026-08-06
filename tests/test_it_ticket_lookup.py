from __future__ import annotations

import pytest

from backend.app.security.entra_auth import AuthenticatedUser
from backend.app.services.onedesk.field_mapping import get_live_it_ticket_field_mapping
from backend.app.services.onedesk.intent_service import OneDeskIntentService
from backend.app.services.onedesk.it_ticket_service import ItTicketService
from backend.app.services.onedesk.ticket_service import (
    _format_latest_ticket,
    _format_specific_ticket,
    _format_summary,
    _format_ticket_list,
)


class FakeSharePointClient:
    async def get_list_columns(self, site_id, list_id):
        return [
            {"name": "Serial_x0020_Number", "displayName": "Serial Number"},
            {"name": "Title", "displayName": "Title"},
            {"name": "Status", "displayName": "Status"},
            {"name": "AssignedTo", "displayName": "Assigned to"},
            {"name": "Author", "displayName": "Created By"},
            {"name": "Priority", "displayName": "Priority"},
            {"name": "Request_Type", "displayName": "Request_Type"},
            {"name": "Nature_x0020_of_x0020_Complain", "displayName": "Nature of Complain"},
            {"name": "Created", "displayName": "Created"},
            {"name": "Modified", "displayName": "Modified"},
        ]

    async def get_list_items(self, site_id, list_id, **kwargs):
        return [
            {
                "id": "1",
                "createdBy": {"user": {"email": "azan@example.com", "id": "oid-1"}},
                "fields": {
                    "Serial_x0020_Number": 520,
                    "Title": "Printer not working properly - Toner Cartridge Issue",
                    "Status": "New",
                    "AssignedTo": None,
                    "Priority": None,
                    "Request_Type": "Network & Infrastructure Support",
                    "Nature_x0020_of_x0020_Complain": "Request A New",
                    "Created": "2026-08-05T09:30:00Z",
                    "Modified": "2026-08-05T10:30:00Z",
                },
            },
            {
                "id": "2",
                "createdBy": {"user": {"email": "azan@example.com"}},
                "fields": {
                    "Serial_x0020_Number": 514,
                    "Title": "Missing items in OPM against advance plan",
                    "Status": "In progress",
                    "AssignedTo": {"displayName": "Hunain Arbani"},
                    "Created": "2026-08-04T09:30:00Z",
                    "Modified": "2026-08-04T10:30:00Z",
                },
            },
            {
                "id": "3",
                "createdBy": {"user": {"email": "other@example.com"}},
                "fields": {
                    "Serial_x0020_Number": 999,
                    "Title": "Other user's ticket",
                    "Status": "Pending",
                    "Created": "2026-08-06T09:30:00Z",
                },
            },
            {
                "id": "4",
                "fields": {
                    "Serial_x0020_Number": 510,
                    "Title": "Resolved request",
                    "Status": "resolved",
                    "Author": {"email": "azan@example.com"},
                    "Created": "2026-08-03T09:30:00Z",
                },
            },
        ]


@pytest.fixture
def current_user():
    return AuthenticatedUser(
        oid="oid-1",
        email="azan@example.com",
        display_name="Azan",
        upn="azan@example.com",
    )


@pytest.fixture
def ticket_service():
    service = ItTicketService(access_token="user-token")
    service._client = FakeSharePointClient()
    service._site_id = "site-id"
    service._list_id = "list-id"
    return service


@pytest.mark.asyncio
async def test_user_only_sees_own_created_by_tickets(ticket_service, current_user):
    tickets = await ticket_service.get_user_tickets(current_user)

    assert [ticket["serial_number"] for ticket in tickets] == [520, 514, 510]
    assert all("Other user's ticket" != ticket["title"] for ticket in tickets)


@pytest.mark.asyncio
async def test_another_users_serial_number_returns_none(ticket_service, current_user):
    assert await ticket_service.get_ticket_by_serial_number(current_user, 999) is None


@pytest.mark.asyncio
async def test_status_buckets_latest_and_summary(ticket_service, current_user):
    open_tickets = await ticket_service.get_open_tickets(current_user)
    closed_tickets = await ticket_service.get_closed_tickets(current_user)
    latest = await ticket_service.get_latest_ticket(current_user)
    summary = await ticket_service.get_ticket_summary(current_user)

    assert [ticket["serial_number"] for ticket in open_tickets] == [520, 514]
    assert [ticket["serial_number"] for ticket in closed_tickets] == [510]
    assert latest["serial_number"] == 520
    assert summary == {
        "open": 2,
        "pending": 0,
        "resolved": 1,
        "closed": 0,
        "total": 3,
    }


def test_real_internal_names_discovered_from_columns():
    mapping = get_live_it_ticket_field_mapping(
        [
            {"name": "Serial_x0020_Number", "displayName": "Serial Number"},
            {"name": "Author", "displayName": "Created By"},
            {"name": "Request_Type", "displayName": "Request_Type"},
            {"name": "Status", "displayName": "Status"},
            {"name": "Title", "displayName": "Title"},
        ]
    )

    assert mapping.ticket_number == "Serial_x0020_Number"
    assert mapping.created_by == "Author"
    assert mapping.request_type == "Request_Type"
    assert mapping.missing_required == []


def test_ticket_intents_route_before_policy_patterns():
    service = OneDeskIntentService()

    assert service.detect("show my tickets").intent_type == "IT_TICKET_LIST"
    assert service.detect("serial number 520 ka status kya hai?").intent_type == "IT_TICKET_SERIAL"
    assert service.detect("Meri latest ticket ka status kya hai?").intent_type == "IT_TICKET_LATEST"
    assert service.detect("what is password policy?").intent_type == "POLICY_QUESTION"


def test_ticket_response_format_excludes_comments_latest_update_and_sources():
    ticket = {
        "serial_number": 520,
        "title": "Printer not working properly - Toner Cartridge Issue",
        "status": "New",
        "assigned_to": "Not assigned",
        "priority": None,
        "request_type": "Network & Infrastructure Support",
        "created_at": "2026-08-05T09:30:00Z",
        "modified_at": "2026-08-05T10:30:00Z",
    }

    combined = "\n\n".join(
        [
            _format_ticket_list("Your open tickets:", [ticket]),
            _format_latest_ticket(ticket),
            _format_summary({"open": 1, "pending": 0, "resolved": 0, "closed": 0, "total": 1}),
            _format_specific_ticket(ticket, "520"),
        ]
    )

    assert "Ticket #520" in combined
    assert "Comment" not in combined
    assert "Latest Update" not in combined
    assert "Sources:" not in combined
    assert "5 August 2026" in combined
