from __future__ import annotations

from fastapi import Header, HTTPException, Request, status

from backend.app.core.config import get_settings
from backend.app.security.current_user import resolve_current_user_from_authorization
from backend.app.security.entra_auth import AuthenticatedUser


async def get_authenticated_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> AuthenticatedUser:
    try:
        user = resolve_current_user_from_authorization(authorization)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed.",
        ) from exc
    request.state.authenticated_user = user
    return user


async def require_authenticated_admin(
    request: Request,
    authorization: str | None = Header(default=None),
    x_oneassist_admin: str | None = Header(default=None),
) -> AuthenticatedUser:
    user = await get_authenticated_user(request, authorization)
    settings = get_settings()

    if settings.enable_entra_auth:
        if settings.azure_admin_role not in user.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin role is required.",
            )
        return user

    if str(x_oneassist_admin or "").lower() not in {"1", "true", "yes"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access is required.",
        )
    return user
