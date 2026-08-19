from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.api.routes import chat as chat_route
from backend.app.integrations.onedesk_api_client import OneDeskApiClient, OneDeskApiError
from backend.app.models.schemas import ChatRequest, ChatResponse


@pytest.mark.asyncio
async def test_existing_user_lookup_is_reused(monkeypatch):
    client = OneDeskApiClient()
    calls: list[tuple[str, dict | None]] = []

    async def fake_get(endpoint, params=None):
        calls.append((endpoint, params))
        return [{"id": 41, "email": "user@example.com"}]

    async def fake_post(*args, **kwargs):
        raise AssertionError("create_user should not be called for an existing user")

    monkeypatch.setattr(client, "get", fake_get)
    monkeypatch.setattr(client, "post", fake_post)

    user = await client.save_user(email="user@example.com", display_name="User")

    assert user["id"] == 41
    assert calls == [("users", {"email": "user@example.com"})]


@pytest.mark.asyncio
async def test_new_user_create(monkeypatch):
    client = OneDeskApiClient()
    created_payloads: list[dict] = []

    async def fake_get(endpoint, params=None):
        return []

    async def fake_post(endpoint, payload):
        created_payloads.append(payload)
        return {"id": 99, "email": payload["email"]}

    monkeypatch.setattr(client, "get", fake_get)
    monkeypatch.setattr(client, "post", fake_post)

    user = await client.save_user(
        email="new@example.com",
        entra_object_id="entra-1",
        display_name="New User",
        department="IT",
        job_title="Analyst",
    )

    assert user["id"] == 99
    assert created_payloads == [
        {
            "entraObjectId": "entra-1",
            "displayName": "New User",
            "email": "new@example.com",
            "department": "IT",
            "jobTitle": "Analyst",
            "isActive": True,
        }
    ]


@pytest.mark.asyncio
async def test_new_chat_session_create_and_message_posts(monkeypatch):
    client = OneDeskApiClient()
    posts: list[tuple[str, dict]] = []

    async def fake_get(endpoint, params=None):
        if endpoint == "users":
            return [{"id": 7, "email": "user@example.com"}]
        return []

    async def fake_post(endpoint, payload):
        posts.append((endpoint, payload))
        if endpoint == "chatsessions":
            return {"id": 55, "sessionUuid": "abc-123"}
        if endpoint == "chatmessages":
            return {"id": len(posts) + 100}
        raise AssertionError(endpoint)

    monkeypatch.setattr(client, "get", fake_get)
    monkeypatch.setattr(client, "post", fake_post)

    result = await client.save_chat_turn(
        user={"id": 7, "email": "user@example.com"},
        session_uuid="abc-123",
        title="New chat",
        question="my hdmi ticket details",
        answer="Ticket #452",
        response_time_ms=321,
        is_answered=True,
    )

    assert [item[0] for item in posts] == ["chatsessions", "chatmessages", "chatmessages"]
    assert posts[1][1]["role"] == "user"
    assert posts[1][1]["userId"] == 7
    assert posts[2][1]["role"] == "assistant"
    assert posts[2][1]["userId"] is None
    assert result["session"]["id"] == 55


@pytest.mark.asyncio
async def test_module_gate_response_persists_via_api(monkeypatch):
    payload = ChatRequest(message="ticket status please", sessionId=uuid4(), activeModule="policies")
    response = ChatResponse(answer="module gate", sources=[], fallback=True, provider="module-router")
    calls: list[dict] = []

    class FakeClient:
        async def save_user(self, **kwargs):
            calls.append({"save_user": kwargs})
            return {"id": 12}

        async def save_chat_turn(self, **kwargs):
            calls.append({"save_chat_turn": kwargs})
            return {
                "session": {"id": 88, "sessionUuid": "sess-88"},
                "user_message": {"id": 501},
                "assistant_message": {"id": 502},
            }

    monkeypatch.setattr(chat_route, "get_onedesk_database_client", lambda: FakeClient())

    result = await chat_route._save_chat_turn_via_onedesk_api(
        payload=payload,
        response=response,
        response_time_ms=42,
        user_email="user@example.com",
        display_name="User",
        department="IT",
    )

    assert result.session_id == 88
    assert calls[0]["save_user"]["email"] == "user@example.com"
    assert calls[1]["save_chat_turn"]["question"] == "ticket status please"
    assert calls[1]["save_chat_turn"]["answer"] == "module gate"


@pytest.mark.asyncio
async def test_api_401_and_unavailable_are_handled_safely(monkeypatch):
    payload = ChatRequest(message="ok", sessionId=uuid4())
    response = ChatResponse(answer="Sure! How else can I help?", sources=[], fallback=False, provider="local-ack")

    class FakeClient:
        async def save_user(self, **kwargs):
            raise OneDeskApiError("OneDesk API returned HTTP 401.")

        async def save_chat_turn(self, **kwargs):
            raise AssertionError("save_chat_turn should not be called after save_user fails")

    monkeypatch.setattr(chat_route, "get_onedesk_database_client", lambda: FakeClient())

    result = await chat_route._save_chat_turn_via_onedesk_api(
        payload=payload,
        response=response,
        response_time_ms=12,
        user_email="user@example.com",
        display_name=None,
        department=None,
    )

    assert result == response
