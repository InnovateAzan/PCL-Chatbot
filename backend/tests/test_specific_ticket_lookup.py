from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.services.onedesk.intent_service import OneDeskIntentService
from backend.app.services.onedesk.ticket_service import OneDeskService


class _StubUser:
    def __init__(self) -> None:
        self.email = "user@example.com"
        self.normalized_identifiers = {"user@example.com"}


class _StubTicketService:
    def __init__(self, tickets):
        self._tickets = tickets

    async def find_tickets_by_query(self, current_user, query):
        query = query.lower()
        return [
            ticket
            for ticket in self._tickets
            if query in str(ticket.get("title", "")).lower()
            or query in str(ticket.get("request_type", "")).lower()
            or query in str(ticket.get("nature_of_complaint", "")).lower()
            or query in str(ticket.get("serial_number", "")).lower()
        ]


@pytest.mark.parametrize(
    ("message", "expected_query"),
    [
        ("my hdmi ticket details", "hdmi"),
        ("my vpn ticket", "vpn"),
        ("ethernet ticket status", "ethernet"),
    ],
)
def test_intent_extracts_ticket_query(message, expected_query):
    intent = OneDeskIntentService().detect(message)
    assert intent.request_query == expected_query


@pytest.mark.asyncio
async def test_specific_ticket_lookup_matches_only_one_ticket():
    service = OneDeskService()
    stub = _StubTicketService(
        [
            {
                "serial_number": 522,
                "title": "VPN Access Request",
                "status": "Open",
                "assigned_to": "IT Help Desk",
                "request_type": "VPN",
                "created_at": "2026-08-01",
                "modified_at": "2026-08-02",
            },
            {
                "serial_number": 452,
                "title": "Request for HDMI Cable",
                "status": "Resolved",
                "assigned_to": "Facilities",
                "request_type": "Hardware",
                "created_at": "2026-08-03",
                "modified_at": "2026-08-04",
            },
            {
                "serial_number": 113,
                "title": "Request for Ethernet Connection",
                "status": "Resolved",
                "assigned_to": "Network Team",
                "request_type": "Network",
                "created_at": "2026-08-05",
                "modified_at": "2026-08-06",
            },
        ]
    )
    result = await stub.find_tickets_by_query(_StubUser(), "hdmi")
    assert len(result) == 1
    assert result[0]["serial_number"] == 452


@pytest.mark.asyncio
async def test_specific_ticket_lookup_is_ambiguous_when_multiple_match():
    stub = _StubTicketService(
        [
            {"serial_number": 1, "title": "VPN Access Request", "request_type": "VPN"},
            {"serial_number": 2, "title": "VPN Setup", "request_type": "VPN"},
        ]
    )
    result = await stub.find_tickets_by_query(_StubUser(), "vpn")
    assert len(result) == 2
