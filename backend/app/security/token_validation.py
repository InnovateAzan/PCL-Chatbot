from __future__ import annotations

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
from backend.app.security.entra_auth import (
    AuthenticatedUser,
    AuthenticationError,
)
from backend.app.security.auth_diagnostics import (
    log_auth_stage,
    public_auth_message,
    token_format_error,
)


class EntraTokenValidator:
    def __init__(self) -> None:
        self.settings = get_settings()

        self.authority = (
            self.settings.effective_azure_authority or ""
        ).rstrip("/")

        self.tenant_id = (
            self.settings.azure_tenant_id or ""
        ).strip()

        # ---------------------------------------------------------
        # IMPORTANT FIX:
        # AZURE_AUTHORITY may already end with /v2.0.
        #
        # Example:
        # https://login.microsoftonline.com/<tenant>/v2.0
        #
        # JWKS endpoint must instead be:
        # https://login.microsoftonline.com/<tenant>/discovery/v2.0/keys
        # ---------------------------------------------------------
        authority_root = self.authority

        if authority_root.lower().endswith("/v2.0"):
            authority_root = authority_root[:-5].rstrip("/")

        self.authority_root = authority_root

        self.jwks_url = (
            f"{self.authority_root}/discovery/v2.0/keys"
            if self.authority_root
            else ""
        )

        self.jwk_client = (
            PyJWKClient(self.jwks_url)
            if self.jwks_url
            else None
        )

    def validate(self, token: str) -> AuthenticatedUser:
        format_error = token_format_error(token)

        if format_error:
            log_auth_stage(
                "api_token_validation",
                token=token,
                result="failed",
                extra={
                    "api_token_validation_result": format_error,
                },
            )

            raise AuthenticationError(
                public_auth_message(format_error),
                code=format_error,
            )

        if not self.jwk_client or not self.authority_root:
            raise AuthenticationError(
                "Microsoft Entra authority is not configured.",
                code="configuration_error",
            )

        audience = (
            self.settings.azure_api_audience
            or self.settings.azure_client_id
        )

        if not audience:
            raise AuthenticationError(
                "Microsoft Entra audience is not configured.",
                code="configuration_error",
            )

        try:
            signing_key = (
                self.jwk_client.get_signing_key_from_jwt(token)
            )

            # Read unverified claims only to determine which valid
            # Microsoft issuer format should be expected.
            unverified_claims = jwt.decode(
                token,
                options={
                    "verify_signature": False,
                    "verify_aud": False,
                    "verify_iss": False,
                    "verify_exp": False,
                },
            )

            token_version = str(
                unverified_claims.get("ver") or ""
            ).strip()

            token_issuer = str(
                unverified_claims.get("iss") or ""
            ).strip()

            expected_issuer = self._resolve_expected_issuer(
                token_version=token_version,
                token_issuer=token_issuer,
            )

            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=audience,
                issuer=expected_issuer,
                options={
                    "require": [
                        "exp",
                        "iss",
                        "aud",
                    ]
                },
            )

        except ExpiredSignatureError as exc:
            self._raise_validation_error(
                token,
                "expired_token",
                exc,
            )

        except InvalidAudienceError as exc:
            self._raise_validation_error(
                token,
                "wrong_audience",
                exc,
            )

        except InvalidIssuerError as exc:
            self._raise_validation_error(
                token,
                "wrong_issuer",
                exc,
            )

        except InvalidSignatureError as exc:
            self._raise_validation_error(
                token,
                "signature_invalid",
                exc,
            )

        except InvalidTokenError as exc:
            self._raise_validation_error(
                token,
                "validation_failed",
                exc,
            )

        except Exception as exc:
            self._raise_validation_error(
                token,
                "validation_failed",
                exc,
            )

        tenant_id = claims.get("tid")

        if (
            self.tenant_id
            and tenant_id != self.tenant_id
        ):
            log_auth_stage(
                "api_token_validation",
                token=token,
                result="failed",
                extra={
                    "api_token_validation_result":
                        "tenant_mismatch",
                },
            )

            raise AuthenticationError(
                public_auth_message(
                    "tenant_mismatch"
                ),
                code="tenant_mismatch",
            )

        preferred_username = claims.get(
            "preferred_username"
        )

        upn = claims.get("upn")

        email = (
            claims.get("email")
            or preferred_username
            or upn
            or claims.get("unique_name")
            or ""
        ).lower()

        if not email:
            raise AuthenticationError(
                (
                    "Token does not include email, "
                    "preferred_username, UPN, or unique_name."
                ),
                code="validation_failed",
            )

        roles = set(
            claims.get("roles") or []
        )

        roles.update(
            claims.get("groups") or []
        )

        log_auth_stage(
            "api_token_validation",
            token=token,
            result="success",
            extra={
                "api_token_validation_result":
                    "success",
            },
        )

        return AuthenticatedUser(
            oid=(
                claims.get("oid")
                or claims.get("sub")
            ),
            email=email,
            display_name=(
                claims.get("name")
                or email
            ),
            preferred_name=claims.get(
                "given_name"
            ),
            upn=upn,
            preferred_username=preferred_username,
            roles=roles,
        )

    def _resolve_expected_issuer(
        self,
        *,
        token_version: str,
        token_issuer: str,
    ) -> str:
        """
        Microsoft Entra access tokens may use different issuer formats.

        v1 token:
        https://sts.windows.net/<tenant-id>/

        v2 token:
        https://login.microsoftonline.com/<tenant-id>/v2.0
        """

        if token_version == "1.0":
            if not self.tenant_id:
                raise AuthenticationError(
                    (
                        "Microsoft Entra tenant ID "
                        "is not configured."
                    ),
                    code="configuration_error",
                )

            return (
                "https://sts.windows.net/"
                f"{self.tenant_id}/"
            )

        if token_version == "2.0":
            if not self.tenant_id:
                raise AuthenticationError(
                    (
                        "Microsoft Entra tenant ID "
                        "is not configured."
                    ),
                    code="configuration_error",
                )

            return (
                "https://login.microsoftonline.com/"
                f"{self.tenant_id}/v2.0"
            )

        # Fallback for an otherwise valid Microsoft token.
        # We still require it to match the configured tenant.
        if token_issuer:
            return token_issuer

        raise AuthenticationError(
            "Microsoft Entra token issuer is missing.",
            code="wrong_issuer",
        )

    @staticmethod
    def _raise_validation_error(
        token: str,
        code: str,
        error: Exception,
    ) -> None:
        log_auth_stage(
            "api_token_validation",
            token=token,
            result="failed",
            extra={
                "api_token_validation_result": code,
            },
        )

        raise AuthenticationError(
            public_auth_message(code),
            code=code,
        ) from error


@lru_cache
def get_entra_token_validator() -> EntraTokenValidator:
    return EntraTokenValidator()