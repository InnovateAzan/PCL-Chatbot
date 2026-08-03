from __future__ import annotations

from functools import lru_cache

import jwt
from jwt import PyJWKClient

from backend.app.core.config import get_settings
from backend.app.security.entra_auth import AuthenticatedUser, AuthenticationError


class EntraTokenValidator:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.authority = self.settings.effective_azure_authority
        self.jwks_url = f"{self.authority}/discovery/v2.0/keys" if self.authority else ""
        self.jwk_client = PyJWKClient(self.jwks_url) if self.jwks_url else None

    def validate(self, token: str) -> AuthenticatedUser:
        if not self.jwk_client or not self.authority:
            raise AuthenticationError("Microsoft Entra authority is not configured.")

        signing_key = self.jwk_client.get_signing_key_from_jwt(token)
        audience = self.settings.azure_api_audience or self.settings.azure_client_id
        if not audience:
            raise AuthenticationError("Microsoft Entra audience is not configured.")

        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=self.authority,
            options={"require": ["exp", "iss", "aud"]},
        )

        tenant_id = claims.get("tid")
        if self.settings.azure_tenant_id and tenant_id != self.settings.azure_tenant_id:
            raise AuthenticationError("Token tenant does not match configured tenant.")

        email = (
            claims.get("email")
            or claims.get("preferred_username")
            or claims.get("upn")
            or ""
        ).lower()
        if not email:
            raise AuthenticationError("Token does not include email or preferred_username.")

        roles = set(claims.get("roles") or [])
        roles.update(claims.get("groups") or [])

        return AuthenticatedUser(
            oid=claims.get("oid") or claims.get("sub"),
            email=email,
            display_name=claims.get("name") or email,
            preferred_name=claims.get("given_name"),
            roles=roles,
        )


@lru_cache
def get_entra_token_validator() -> EntraTokenValidator:
    return EntraTokenValidator()
