from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.models.schemas import ChatResponse
from backend.app.services.onedesk.intent_service import OneDeskIntentService
from backend.app.services.onedesk import ticket_service as ticket_service_module
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


class _StubOneDeskTicketService:
    def __init__(self, tickets_by_email):
        self._tickets_by_email = tickets_by_email

    async def find_tickets_by_query(self, current_user, query):
        query = query.lower()
        tickets = self._tickets_by_email.get(current_user.email, [])
        return [
            ticket
            for ticket in tickets
            if query in str(ticket.get("title", "")).lower()
            or query in str(ticket.get("request_type", "")).lower()
            or query in str(ticket.get("nature_of_complaint", "")).lower()
            or query in str(ticket.get("description", "")).lower()
            or query in str(ticket.get("serial_number", "")).lower()
        ]


class _StubAuthUser:
    def __init__(self, email="user@example.com"):
        self.email = email
        self.normalized_identifiers = {email}


def _make_service(monkeypatch, tickets_by_email):
    service = OneDeskService()
    service.settings.enable_onedesk_it_read = True
    service.settings.enable_onedesk_integration = False
    monkeypatch.setattr(ticket_service_module, "resolve_current_user_from_authorization", lambda value: _StubAuthUser())
    monkeypatch.setattr(ticket_service_module, "ItTicketService", lambda access_token=None: _StubOneDeskTicketService(tickets_by_email))
    return service


@pytest.mark.parametrize(
    ("message", "expected_query"),
    [
        ("provide my hdmi complain details", "hdmi"),
        ("my hdmi ticket", "hdmi"),
        ("hdmi request", "hdmi"),
        ("ticket 452", None),
        ("my vpn ticket", "vpn"),
        ("ethernet ticket status", "ethernet"),
    ],
)
def test_intent_extracts_ticket_query(message, expected_query):
    intent = OneDeskIntentService().detect(message)
    assert intent.request_query == expected_query


def test_intent_detects_numbered_ticket():
    intent = OneDeskIntentService().detect("ticket 452")
    assert intent.request_number == "452"


@pytest.mark.asyncio
async def test_specific_ticket_lookup_matches_only_one_ticket(monkeypatch):
    service = _make_service(
        monkeypatch,
        {
            "user@example.com": [
                {
                    "serial_number": 522,
                    "title": "VPN Access Request",
                    "status": "Open",
                    "assigned_to": "IT Help Desk",
                    "request_type": "VPN",
                    "description": "Need VPN access",
                    "created_at": "2026-08-01",
                    "modified_at": "2026-08-02",
                },
                {
                    "serial_number": 452,
                    "title": "Request for HDMI Cable",
                    "status": "Resolved",
                    "assigned_to": "Facilities",
                    "request_type": "Hardware",
                    "description": "HDMI cable request",
                    "created_at": "2026-08-03",
                    "modified_at": "2026-08-04",
                },
                {
                    "serial_number": 113,
                    "title": "Request for Ethernet Connection",
                    "status": "Resolved",
                    "assigned_to": "Network Team",
                    "request_type": "Network",
                    "description": "Ethernet connectivity issue",
                    "created_at": "2026-08-05",
                    "modified_at": "2026-08-06",
                },
            ]
        },
    )

    response = await service.answer(
        message="provide my hdmi complain details",
        user_email="user@example.com",
        access_token="token",
    )

    assert "Ticket #452" in response.answer
    assert "HDMI" in response.answer


@pytest.mark.asyncio
async def test_specific_ticket_lookup_is_ambiguous_when_multiple_match(monkeypatch):
    service = _make_service(
        monkeypatch,
        {
            "user@example.com": [
                {"serial_number": 1, "title": "VPN Access Request", "request_type": "VPN"},
                {"serial_number": 2, "title": "VPN Setup", "request_type": "VPN"},
            ]
        },
    )

    response = await service.answer(
        message="vpn request",
        user_email="user@example.com",
        access_token="token",
    )

    assert "multiple matching tickets" in response.answer.lower()


@pytest.mark.asyncio
async def test_specific_ticket_lookup_does_not_match_other_users_ticket(monkeypatch):
    service = _make_service(
        monkeypatch,
        {
            "user@example.com": [
                {"serial_number": 452, "title": "Request for HDMI Cable", "request_type": "Hardware"}
            ],
            "other@example.com": [
                {"serial_number": 999, "title": "HDMI Request", "request_type": "Hardware"}
            ],
        },
    )

    response = await service.answer(
        message="my hdmi ticket",
        user_email="user@example.com",
        access_token="token",
    )

    assert "Ticket #452" in response.answer
    assert "999" not in response.answer
