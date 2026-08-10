from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from jwt import ExpiredSignatureError, InvalidAudienceError

from backend.app.integrations.microsoft.graph_errors import GraphConfigurationError
from backend.app.integrations.microsoft.obo_service import OnBehalfOfService
from backend.app.security.auth_diagnostics import (
    safe_token_diagnostics,
    token_format_error,
)
from backend.app.security.entra_auth import AuthenticatedUser, AuthenticationError
from backend.app.security.token_validation import EntraTokenValidator
from backend.app.services.onedesk.field_mapping import get_live_it_ticket_field_mapping
from backend.app.services.onedesk.it_ticket_service import ItTicketService


EXPECTED_AUDIENCE = "api://befd94d3-9bc9-414f-81ec-a89a041384f7"
EXPECTED_ISSUER = (
    "https://login.microsoftonline.com/"
    "d4a5cecc-db51-4781-8bb7-e565febf78b1/v2.0"
)


def _jwt(claims: dict) -> str:
    header = {"alg": "RS256", "typ": "JWT"}
    return ".".join(
        [
            _b64(header),
            _b64(claims),
            "signature-placeholder-long-enough",
        ]
    )


def _b64(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _future_token(**claims) -> str:
    payload = {
        "aud": EXPECTED_AUDIENCE,
        "iss": EXPECTED_ISSUER,
        "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        "tid": "d4a5cecc-db51-4781-8bb7-e565febf78b1",
        "preferred_username": "azan@example.com",
        "oid": "oid-1",
        "name": "Azan",
        **claims,
    }
    return _jwt(payload)


def test_safe_diagnostics_do_not_expose_token_and_detect_valid_shape():
    token = _future_token()

    diagnostics = safe_token_diagnostics(token)

    assert diagnostics["token_present"] is True
    assert diagnostics["token_length"] == len(token)
    assert diagnostics["jwt_segment_count"] == 3
    assert diagnostics["token_audience"] == EXPECTED_AUDIENCE
    assert diagnostics["token_issuer"] == EXPECTED_ISSUER
    assert token not in str(diagnostics)
    assert token_format_error(token) is None


def test_missing_expired_and_wrong_audience_token_detection(monkeypatch):
    expired = _future_token(
        exp=int((datetime.now(UTC) - timedelta(minutes=1)).timestamp())
    )

    assert token_format_error(None) == "token_missing"
    assert token_format_error("abc") == "token_too_short"
    assert token_format_error("a.b") == "token_too_short"
    assert token_format_error(expired) == "expired_token"

    validator = EntraTokenValidator.__new__(EntraTokenValidator)
    validator.settings = SimpleNamespace(
        azure_api_audience=EXPECTED_AUDIENCE,
        azure_client_id="befd94d3-9bc9-414f-81ec-a89a041384f7",
        azure_tenant_id="d4a5cecc-db51-4781-8bb7-e565febf78b1",
    )
    validator.authority = EXPECTED_ISSUER
    validator.jwk_client = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key="key")
    )

    def raise_wrong_audience(*args, **kwargs):
        raise InvalidAudienceError("bad audience")

    monkeypatch.setattr(
        "backend.app.security.token_validation.jwt.decode",
        raise_wrong_audience,
    )

    with pytest.raises(AuthenticationError) as error:
        validator.validate(_future_token(aud="https://graph.microsoft.com"))

    assert error.value.code == "wrong_audience"


def test_validator_maps_expired_signature(monkeypatch):
    validator = EntraTokenValidator.__new__(EntraTokenValidator)
    validator.settings = SimpleNamespace(
        azure_api_audience=EXPECTED_AUDIENCE,
        azure_client_id="befd94d3-9bc9-414f-81ec-a89a041384f7",
        azure_tenant_id="d4a5cecc-db51-4781-8bb7-e565febf78b1",
    )
    validator.authority = EXPECTED_ISSUER
    validator.jwk_client = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key="key")
    )

    def raise_expired(*args, **kwargs):
        raise ExpiredSignatureError("expired")

    monkeypatch.setattr(
        "backend.app.security.token_validation.jwt.decode",
        raise_expired,
    )

    with pytest.raises(AuthenticationError) as error:
        validator.validate(_future_token())

    assert error.value.code == "expired_token"


@pytest.mark.asyncio
async def test_obo_success_and_failure(monkeypatch):
    settings = SimpleNamespace(
        enable_entra_auth=True,
        azure_client_id="befd94d3-9bc9-414f-81ec-a89a041384f7",
        azure_client_secret="configured-secret",
        effective_azure_authority=EXPECTED_ISSUER,
        azure_obo_scopes=(
            "https://graph.microsoft.com/User.Read "
            "https://graph.microsoft.com/Sites.Read.All"
        ),
    )
    monkeypatch.setattr(
        "backend.app.integrations.microsoft.obo_service.get_settings",
        lambda: settings,
    )

    class SuccessClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, data):
            return httpx.Response(200, json={"access_token": "graph-token"})

    monkeypatch.setattr(
        "backend.app.integrations.microsoft.obo_service.httpx.AsyncClient",
        SuccessClient,
    )
    assert await OnBehalfOfService().exchange(_future_token()) == "graph-token"

    class FailureClient(SuccessClient):
        async def post(self, url, data):
            return httpx.Response(
                400,
                json={
                    "error": "invalid_grant",
                    "error_description": "expired assertion",
                },
            )

    monkeypatch.setattr(
        "backend.app.integrations.microsoft.obo_service.httpx.AsyncClient",
        FailureClient,
    )
    with pytest.raises(GraphConfigurationError) as error:
        await OnBehalfOfService().exchange(_future_token())

    assert error.value.code == "invalid_grant"


@pytest.mark.asyncio
async def test_ticket_522_lookup_after_successful_authentication():
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
                        "Title": "VPN access request",
                        "Status": "In progress",
                        "Author": {"email": "azan@example.com"},
                        "Created": "2026-08-06T09:30:00Z",
                    },
                }
            ]

    service = ItTicketService(access_token=_future_token())
    service._client = FakeSharePointClient()
    service._site_id = "site-id"
    service._list_id = "list-id"
    current_user = AuthenticatedUser(
        oid="oid-1",
        email="azan@example.com",
        display_name="Azan",
        upn="azan@example.com",
    )

    ticket = await service.get_ticket_by_serial_number(current_user, 522)

    assert ticket["serial_number"] == 522
    assert ticket["status"] == "In progress"


def test_frontend_and_spfx_token_contract_and_refresh_logic():
    app_js = Path("frontend/app.js").read_text(encoding="utf-8")
    spfx_ts = Path(
        "sharepoint-spfx/src/extensions/pclGpt/PclGptApplicationCustomizer.ts"
    ).read_text(encoding="utf-8")

    assert 'const API_TOKEN_MESSAGE_TYPE = "onedesk-api-token";' in app_js
    assert "isApiTokenMessage(payload)" in app_js
    assert "value.length" in app_js
    assert "function jwtSegmentCount(" in app_js
    assert "response.status !== 401" in app_js
    assert "forceRefresh: true" in app_js
    assert "Bearer undefined" not in app_js
    assert "Bearer null" not in app_js

    assert (
        'const DEFAULT_API_RESOURCE = "api://befd94d3-9bc9-414f-81ec-a89a041384f7";'
        in spfx_ts
    )
    assert 'type: API_TOKEN_MESSAGE_TYPE' in spfx_ts
    assert 'provider.getToken(resource)' in spfx_ts
