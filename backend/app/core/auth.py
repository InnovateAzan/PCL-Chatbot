from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import jwt
from jwt import PyJWKClient

from backend.app.core.config import get_settings


@dataclass(frozen=True)
class TokenIdentity:
    entra_object_id: str | None
    email: str
    display_name: str
    preferred_name: str | None
    roles: set[str]


class EntraTokenValidator:
    def __init__(self) -> None:
        self.settings = get_settings()
        tenant_id = self.settings.azure_tenant_id
        self.issuer = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
        self.jwks_url = f"{self.issuer}/discovery/v2.0/keys"
        self.jwk_client = PyJWKClient(self.jwks_url)

    def validate(self, token: str) -> TokenIdentity:
        signing_key = self.jwk_client.get_signing_key_from_jwt(token)
        audience = (
            self.settings.azure_api_audience
            or self.settings.azure_client_id
        )
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=self.issuer,
            options={"require": ["exp", "iss", "aud"]},
        )

        roles = set(claims.get("roles") or [])
        roles.update(claims.get("groups") or [])

        email = (
            claims.get("email")
            or claims.get("preferred_username")
            or claims.get("upn")
            or ""
        ).lower()

        if not email:
            raise ValueError("Token does not include a usable email claim.")

        return TokenIdentity(
            entra_object_id=claims.get("oid") or claims.get("sub"),
            email=email,
            display_name=claims.get("name") or email,
            preferred_name=claims.get("given_name"),
            roles=roles,
        )


@lru_cache
def get_entra_validator() -> EntraTokenValidator:
    return EntraTokenValidator()
