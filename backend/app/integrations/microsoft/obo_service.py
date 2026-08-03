from __future__ import annotations

from backend.app.core.config import get_settings
from backend.app.integrations.microsoft.graph_errors import GraphConfigurationError


class OnBehalfOfService:
    """Placeholder for Microsoft OBO token exchange.

    Live exchange remains disabled until the Entra app registration and scopes
    are finalized. The service exists so Graph clients do not need rewriting.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    async def exchange(self, user_access_token: str) -> str:
        if not self.settings.enable_entra_auth:
            raise GraphConfigurationError("OBO exchange requires ENABLE_ENTRA_AUTH=true.")
        if not self.settings.azure_client_id or not self.settings.azure_client_secret:
            raise GraphConfigurationError("Azure client credentials are not configured.")
        return user_access_token
