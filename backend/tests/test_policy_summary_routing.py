from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app.models.schemas import ChatRequest, ChatResponse
from backend.app.services.chat_history import ChatHistoryService
from backend.app.services.onedesk.intent_service import OneDeskIntentService
from backend.app.services import chat_history as chat_history_module


class _FakeChatbot:
    def answer(self, message: str, **kwargs):
        return ChatResponse(answer=f"POLICY:{message}", sources=[], fallback=False, provider="policy-rag")


class _FakeMessages:
    async def create(self, **kwargs):
        return SimpleNamespace(id=1)

    async def latest_active_policy_context(self, **kwargs):
        return None


class _FakeSessions:
    async def get_owned(self, **kwargs):
        return SimpleNamespace(id=uuid4(), status="ACTIVE")

    async def increment_message_count(self, *args, **kwargs):
        return None


class _FakeSources:
    async def save_sources(self, **kwargs):
        return None


class _FakeUnanswered:
    async def upsert_occurrence(self, **kwargs):
        return None


class _FakeAudit:
    async def create(self, **kwargs):
        return None


class _FakeDbSession:
    async def commit(self):
        return None

    async def rollback(self):
        return None


class _FakeOneDesk:
    def get_ticket_context(self, session_key: str):
        return None

    def should_handle(self, *args, **kwargs):
        return False

    async def answer(self, *args, **kwargs):
        return ChatResponse(answer="TICKET", sources=[], fallback=False, provider="onedesk")


@pytest.mark.parametrize(
    ("message", "expected_intent"),
    [
        ("Access Control policy summary", "POLICY_QUESTION"),
        ("Information Security policy summary", "POLICY_QUESTION"),
        ("Backup & Disaster Recovery policy summary", "POLICY_QUESTION"),
        ("Incident Response policy summary", "POLICY_QUESTION"),
        ("Vendor & Third-Party Risk key responsibilities", "POLICY_QUESTION"),
    ],
)
def test_policy_summary_intent_routes_to_policy(message, expected_intent):
    intent = OneDeskIntentService().detect(message)
    assert intent.intent_type == expected_intent
    assert intent.module == "policy"


@pytest.mark.parametrize(
    ("message", "expected_intent"),
    [
        ("ticket summary", "IT_TICKET_SUMMARY"),
        ("show my ticket summary", "IT_TICKET_SUMMARY"),
        ("show my open tickets", "IT_TICKET_OPEN"),
    ],
)
def test_ticket_summary_intent_stays_ticket(message, expected_intent):
    intent = OneDeskIntentService().detect(message)
    assert intent.intent_type == expected_intent
    assert intent.module == "it"


def test_mixed_intent_is_detected():
    intent = OneDeskIntentService().detect("show my tickets and explain Access Control policy")
    assert intent.intent_type == "MIXED"
    assert intent.module is None


@pytest.mark.parametrize(
    "message",
    [
        "Incident Response policy summary",
        "Access Control policy summary",
        "Information Security policy summary",
        "Backup & Disaster Recovery policy summary",
        "Vendor & Third-Party Risk key responsibilities",
    ],
)
def test_policy_name_priority_stays_policy(message):
    intent = OneDeskIntentService().detect(message)
    assert intent.intent_type == "POLICY_QUESTION"
    assert intent.module == "policy"


@pytest.mark.asyncio
async def test_policy_summary_message_routes_to_policy_rag(monkeypatch):
    db_session = _FakeDbSession()
    service = ChatHistoryService(db_session, _FakeChatbot())
    service.sessions = _FakeSessions()
    service.messages = _FakeMessages()
    service.sources = _FakeSources()
    service.unanswered = _FakeUnanswered()
    service.audit = _FakeAudit()
    monkeypatch.setattr(chat_history_module, "OneDeskService", lambda: _FakeOneDesk())

    response = await service.answer(
        user=SimpleNamespace(id=1, email="user@example.com", display_name="User", preferred_name="User"),
        session_id=uuid4(),
        message="Access Control policy summary",
        active_module="policies",
    )

    assert response.answer.startswith("POLICY:")
