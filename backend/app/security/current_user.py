from __future__ import annotations

import logging

from backend.app.core.config import get_settings
from backend.app.security.entra_auth import AuthenticatedUser
from backend.app.security.token_validation import get_entra_token_validator

logger = logging.getLogger(__name__)


def resolve_current_user_from_authorization(
    authorization: str | None,
) -> AuthenticatedUser:
    settings = get_settings()

    if settings.enable_entra_auth:
        if not authorization or not authorization.lower().startswith("bearer "):
            if settings.environment.lower() in {"development", "dev", "local"}:
                return _development_user()
            raise PermissionError("Bearer token is required.")
        token = authorization.split(" ", 1)[1].strip()
        return get_entra_token_validator().validate(token)

    if settings.environment.lower() not in {"development", "dev", "local"}:
        raise PermissionError("Development identity fallback is disabled outside development.")

    logger.warning(
        "Microsoft Entra authentication is disabled; using development identity provider."
    )
    return _development_user()


def _development_user() -> AuthenticatedUser:
    settings = get_settings()
    logger.warning(
        "Using development OneAssist identity provider; never enable this in production."
    )
    return AuthenticatedUser(
        oid="development-user",
        email="development.oneassist.user@example.com",
        display_name="Development OneAssist User",
        preferred_name="Development",
        upn="development.oneassist.user@example.com",
        preferred_username="development.oneassist.user@example.com",
        roles={settings.azure_admin_role, settings.azure_user_role},
        is_development_identity=True,
    )
