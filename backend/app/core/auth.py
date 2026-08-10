from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import jwt
from jwt import (
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    InvalidTokenError,
    PyJWKClient,
)

from backend.app.core.config import get_settings
from backend.app.security.auth_diagnostics import (
    log_auth_stage,
    public_auth_message,
    token_format_error,
)
from backend.app.security.entra_auth import AuthenticationError


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
        format_error = token_format_error(token)
        if format_error:
            log_auth_stage(
                "fastapi_api_token_validation",
                token=token,
                result="failed",
                extra={"api_token_validation_result": format_error},
            )
            raise AuthenticationError(
                public_auth_message(format_error),
                code=format_error,
            )

        audience = (
            self.settings.azure_api_audience
            or self.settings.azure_client_id
        )
        try:
            signing_key = self.jwk_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=audience,
                issuer=self.issuer,
                options={"require": ["exp", "iss", "aud"]},
            )
        except ExpiredSignatureError as exc:
            self._raise_validation_error(token, "expired_token", exc)
        except InvalidAudienceError as exc:
            self._raise_validation_error(token, "wrong_audience", exc)
        except InvalidIssuerError as exc:
            self._raise_validation_error(token, "wrong_issuer", exc)
        except InvalidSignatureError as exc:
            self._raise_validation_error(token, "signature_invalid", exc)
        except InvalidTokenError as exc:
            self._raise_validation_error(token, "validation_failed", exc)

        roles = set(claims.get("roles") or [])
        roles.update(claims.get("groups") or [])

        email = (
            claims.get("email")
            or claims.get("preferred_username")
            or claims.get("upn")
            or ""
        ).lower()

        if not email:
            raise AuthenticationError(
                "Token does not include a usable email claim.",
                code="validation_failed",
            )

        log_auth_stage(
            "fastapi_api_token_validation",
            token=token,
            result="success",
            extra={"api_token_validation_result": "success"},
        )

        return TokenIdentity(
            entra_object_id=claims.get("oid") or claims.get("sub"),
            email=email,
            display_name=claims.get("name") or email,
            preferred_name=claims.get("given_name"),
            roles=roles,
        )

    @staticmethod
    def _raise_validation_error(
        token: str,
        code: str,
        error: Exception,
    ) -> None:
        log_auth_stage(
            "fastapi_api_token_validation",
            token=token,
            result="failed",
            extra={"api_token_validation_result": code},
        )
        raise AuthenticationError(
            public_auth_message(code),
            code=code,
        ) from error


@lru_cache
def get_entra_validator() -> EntraTokenValidator:
    return EntraTokenValidator()
