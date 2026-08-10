from types import SimpleNamespace
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.api.routes import chat as chat_route
from backend.app.api.routes import users as users_route
from backend.app.models.schemas import ChatRequest, ChatResponse, UserInitializeRequest


def _database_disabled_settings():
    return SimpleNamespace(enable_database=False)


@pytest.mark.asyncio
async def test_users_initialize_succeeds_without_database(monkeypatch):
    async def fail_initialize_user(self, payload):
        raise AssertionError("database-backed user initialization should be skipped")

    monkeypatch.setattr(users_route, "get_settings", _database_disabled_settings)
    monkeypatch.setattr(
        users_route.UserService,
        "initialize_user",
        fail_initialize_user,
    )

    response = await users_route.initialize_user(
        UserInitializeRequest(
            displayName="Azan",
            preferredName="Azan",
            email="azan@example.com",
            employeeId="E-1",
            department="IT",
            jobTitle="Engineer",
            entraObjectId="oid-1",
        ),
        db_session=None,
    )

    assert response.user_id == 0
    assert response.profile.email == "azan@example.com"
    assert response.profile.display_name == "Azan"
    assert response.profile.department == "IT"


@pytest.mark.asyncio
async def test_chat_ticket_request_skips_database_when_disabled(monkeypatch):
    class FakeOneDeskService:
        def should_handle(self, message):
            return "ticket" in message.lower()

        async def answer(self, message, user_email, access_token):
            return ChatResponse(
                answer="Ticket 522 is In Progress.",
                provider="onedesk-live",
            )

    def fail_persist(**kwargs):
        raise AssertionError("existing postgres persistence should be skipped")

    monkeypatch.setattr(chat_route, "get_settings", _database_disabled_settings)
    monkeypatch.setattr(chat_route, "get_onedesk_service", lambda: FakeOneDeskService())
    monkeypatch.setattr(chat_route, "persist_chat_best_effort", fail_persist)

    response = await chat_route.chat(
        payload=ChatRequest(
            message="ticket 522 status",
            userEmail="azan@example.com",
        ),
        x_oneassist_user_id=123,
        authorization="Bearer graph-token",
        existing_db=None,
    )

    assert response.answer == "Ticket 522 is In Progress."
    assert response.provider == "onedesk-live"


@pytest.mark.asyncio
async def test_chat_policy_answer_skips_database_when_disabled(monkeypatch):
    class FakeOneDeskService:
        def should_handle(self, message):
            return False

    class FakeChatbot:
        def answer(self, message, user_display_name=None, preferred_name=None):
            return ChatResponse(
                answer="Password resets are covered by the access policy.",
                provider="policy-rules",
            )

    def fail_persist(**kwargs):
        raise AssertionError("existing postgres persistence should be skipped")

    monkeypatch.setattr(chat_route, "get_settings", _database_disabled_settings)
    monkeypatch.setattr(chat_route, "get_onedesk_service", lambda: FakeOneDeskService())
    monkeypatch.setattr(chat_route, "get_chatbot", lambda: FakeChatbot())
    monkeypatch.setattr(chat_route, "persist_chat_best_effort", fail_persist)

    response = await chat_route.chat(
        payload=ChatRequest(
            message="what is the password reset policy?",
            displayName="Azan",
            preferredName="Azan",
        ),
        x_oneassist_user_id=123,
        authorization=None,
        existing_db=None,
    )

    assert response.answer == "Password resets are covered by the access policy."
    assert response.provider == "policy-rules"
