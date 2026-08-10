from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.core import logging_config
from backend.app.core.logging_config import (
    configure_logging,
    install_exception_handlers,
    install_request_logging,
    log_event,
    sanitize_log_data,
)
from backend.app.integrations.microsoft.graph_client import GraphClient
from backend.app.security.auth_diagnostics import log_auth_stage
from backend.app.services.onedesk.it_ticket_service import ItTicketService
from backend.app.security.entra_auth import AuthenticatedUser


def test_logging_configuration_creates_rotating_files(tmp_path, monkeypatch):
    settings = SimpleNamespace(
        log_level="INFO",
        log_file=str(tmp_path / "oneassist.log"),
        log_error_file=str(tmp_path / "oneassist-error.log"),
        log_max_bytes=1024,
        log_backup_count=2,
        log_json=False,
    )
    monkeypatch.setattr(logging_config, "get_settings", lambda: settings)
    monkeypatch.setattr(logging_config, "_configured", False)

    configure_logging()
    logging.getLogger("test").info("hello")

    assert (tmp_path / "oneassist.log").exists()
    assert (tmp_path / "oneassist-error.log").exists()
    assert any(
        handler.__class__.__name__ == "RotatingFileHandler"
        for handler in logging.getLogger().handlers
    )


def test_redaction_removes_tokens_secrets_and_database_passwords():
    payload = sanitize_log_data(
        {
            "access_token": "header.payload.signature",
            "client_secret": "super-secret",
            "authorization": "Bearer header.payload.signature",
            "database_url": "postgresql://user:pass@example/db",
            "email": "azan@example.com",
        }
    )

    rendered = str(payload)

    assert "header.payload.signature" not in rendered
    assert "super-secret" not in rendered
    assert "user:pass" not in rendered
    assert "a***@example.com" in rendered


def test_request_id_generation_and_response_header():
    app = FastAPI()
    install_request_logging(app)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    response = TestClient(app).get("/ping", headers={"X-Request-ID": "req-12345"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-12345"


def test_global_exception_handler_includes_request_id(monkeypatch):
    monkeypatch.setattr(
        logging_config,
        "get_settings",
        lambda: SimpleNamespace(environment="development"),
    )
    app = FastAPI()
    install_request_logging(app)
    install_exception_handlers(app)

    @app.get("/boom")
    async def boom():
        raise RuntimeError("failed safely")

    response = TestClient(app, raise_server_exceptions=False).get(
        "/boom",
        headers={"X-Request-ID": "req-boom"},
    )

    assert response.status_code == 500
    assert response.json()["request_id"] == "req-boom"


def test_auth_diagnostics_log_safe_fields_only(caplog):
    caplog.set_level(logging.INFO)
    token = "a" * 120 + "." + "b" * 20 + "." + "c" * 20

    log_auth_stage("api_token_validation", token=token, result="failed")

    record = caplog.records[-1]
    fields = record.safe_fields

    assert token not in str(fields)
    assert fields["token_length"] == len(token)
    assert fields["jwt_segment_count"] == 3


@pytest.mark.asyncio
async def test_graph_error_is_safely_logged(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def request(self, *args, **kwargs):
            return httpx.Response(
                403,
                json={
                    "error": {
                        "code": "accessDenied",
                        "message": "Access denied.",
                    }
                },
                headers={"request-id": "graph-request-id"},
            )

    monkeypatch.setattr(
        "backend.app.integrations.microsoft.graph_client.httpx.AsyncClient",
        FakeAsyncClient,
    )

    client = GraphClient(access_token="graph-token")
    with pytest.raises(Exception):
        await client.get("sites/site-id/lists/list-id/items")

    record = caplog.records[-1]
    fields = record.safe_fields

    assert record.event_name == "graph_request_failed"
    assert fields["graph_error_code"] == "accessDenied"
    assert "graph-token" not in caplog.text


@pytest.mark.asyncio
async def test_ticket_lookup_lifecycle_logs(caplog):
    caplog.set_level(logging.INFO)

    class FakeSharePointClient:
        async def get_list_columns(self, site_id, list_id):
            return [
                {"name": "Serial_x0020_Number", "displayName": "Serial Number"},
                {"name": "Title", "displayName": "Title"},
                {"name": "Status", "displayName": "Status"},
                {"name": "Author", "displayName": "Created By"},
                {"name": "Created", "displayName": "Created"},
            ]

        async def get_list_items(self, site_id, list_id, **kwargs):
            return [
                {
                    "id": "522",
                    "createdBy": {"user": {"email": "azan@example.com"}},
                    "fields": {
                        "Serial_x0020_Number": 522,
                        "Title": "Do not log full title",
                        "Status": "New",
                        "Author": {"email": "azan@example.com"},
                    },
                }
            ]

    service = ItTicketService(access_token="user-token")
    service._client = FakeSharePointClient()
    service._site_id = "site-id"
    service._list_id = "list-id"
    user = AuthenticatedUser(
        oid="oid-1",
        email="azan@example.com",
        display_name="Azan",
    )

    ticket = await service.get_ticket_by_serial_number(user, 522)

    assert ticket["serial_number"] == 522
    assert "ticket_lookup_started" in caplog.text
    assert "ticket_lookup_completed" in caplog.text
    assert "Do not log full title" not in caplog.text


def test_policy_and_database_log_events_do_not_require_content(caplog):
    caplog.set_level(logging.INFO)
    logger = logging.getLogger("test.policy")

    log_event(
        logger,
        "policy_retrieval_started",
        query_hash="abc123",
        detected_intent="Asset Damage",
        original_query=None,
    )
    log_event(
        logger,
        "database_save_failed",
        error_code="DATABASE_SAVE_FAILED",
        exception_type="OperationalError",
    )

    assert "policy_retrieval_started" in caplog.text
    assert "database_save_failed" in caplog.text
    assert "My laptop is broken" not in caplog.text
