from __future__ import annotations

import httpx

from backend.app.core.config import get_settings
from backend.app.integrations.microsoft.graph_errors import GraphConfigurationError
from backend.app.security.auth_diagnostics import log_auth_stage


SAFE_OBO_ERROR_CODES = {
    "invalid_client",
    "invalid_grant",
    "invalid_scope",
    "consent_required",
    "expired_assertion",
}


class OnBehalfOfService:
    """Exchange a validated OneDesk API token for a Microsoft Graph token."""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def exchange(self, user_access_token: str) -> str:
        if not self.settings.enable_entra_auth:
            raise GraphConfigurationError("OBO exchange requires ENABLE_ENTRA_AUTH=true.")
        if not self.settings.azure_client_id or not self.settings.azure_client_secret:
            raise GraphConfigurationError("Azure client credentials are not configured.")
        if not self.settings.effective_azure_authority:
            raise GraphConfigurationError("Azure authority is not configured.")
        scopes = " ".join(self.settings.azure_obo_scopes.split())
        if not scopes:
            raise GraphConfigurationError("Azure OBO scopes are not configured.")

        token_url = f"{self.settings.effective_azure_authority}/oauth2/v2.0/token"
        log_auth_stage(
            "obo_exchange_started",
            token=user_access_token,
            result="started",
            extra={
                "obo_exchange_result": "started",
                "scope_count": len(scopes.split()),
            },
        )
        data = {
            "client_id": self.settings.azure_client_id,
            "client_secret": self.settings.azure_client_secret,
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "requested_token_use": "on_behalf_of",
            "assertion": user_access_token,
            "scope": scopes,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(token_url, data=data)
        except httpx.TimeoutException as exc:
            log_auth_stage(
                "obo_exchange",
                token=user_access_token,
                result="failed",
                extra={"obo_exchange_result": "timeout"},
            )
            raise GraphConfigurationError("OBO exchange timed out.") from exc
        except httpx.HTTPError as exc:
            log_auth_stage(
                "obo_exchange",
                token=user_access_token,
                result="failed",
                extra={"obo_exchange_result": "http_error"},
            )
            raise GraphConfigurationError("OBO exchange failed.") from exc

        if response.is_error:
            safe_code, safe_description = _safe_obo_error(response)
            log_auth_stage(
                "obo_exchange",
                token=user_access_token,
                result="failed",
                extra={
                    "obo_exchange_result": safe_code,
                    "obo_status_code": response.status_code,
                },
            )
            raise GraphConfigurationError(
                f"OBO exchange failed: {safe_code}",
                code=safe_code,
                details={
                    "status_code": response.status_code,
                    "error": safe_code,
                    "error_description": safe_description,
                },
            )

        payload = response.json()
        graph_token = str(payload.get("access_token") or "")
        if not graph_token:
            log_auth_stage(
                "obo_exchange",
                token=user_access_token,
                result="failed",
                extra={"obo_exchange_result": "missing_access_token"},
            )
            raise GraphConfigurationError(
                "OBO exchange did not return a Graph token.",
                code="missing_access_token",
            )
        log_auth_stage(
            "obo_exchange",
            token=user_access_token,
            result="success",
            extra={"obo_exchange_result": "success"},
        )
        return graph_token


def _safe_obo_error(response: httpx.Response) -> tuple[str, str | None]:
    try:
        payload = response.json()
    except ValueError:
        return "obo_failed", None

    raw_code = str(payload.get("error") or "obo_failed").strip()
    raw_description = str(payload.get("error_description") or "").strip()

    normalized_description = raw_description.lower()
    if raw_code not in SAFE_OBO_ERROR_CODES:
        if "expired" in normalized_description and "assertion" in normalized_description:
            raw_code = "expired_assertion"
        elif "consent" in normalized_description:
            raw_code = "consent_required"
        else:
            raw_code = "obo_failed"

    return raw_code, raw_description[:500] or None
