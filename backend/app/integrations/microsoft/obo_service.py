from __future__ import annotations

import httpx

from backend.app.core.config import get_settings
from backend.app.integrations.microsoft.graph_errors import GraphConfigurationError


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
            raise GraphConfigurationError("OBO exchange timed out.") from exc
        except httpx.HTTPError as exc:
            raise GraphConfigurationError("OBO exchange failed.") from exc

        if response.is_error:
            raise GraphConfigurationError("OBO exchange failed.")

        payload = response.json()
        graph_token = str(payload.get("access_token") or "")
        if not graph_token:
            raise GraphConfigurationError("OBO exchange did not return a Graph token.")
        return graph_token
