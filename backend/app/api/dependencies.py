from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import get_entra_validator
from backend.app.core.config import get_settings
from backend.app.core.database import get_db_session
from backend.app.models.chat_history import ChatbotUser
from backend.app.repositories.chat_history import UserRepository
from backend.app.security.auth_diagnostics import public_auth_message, token_format_error
from backend.app.security.entra_auth import AuthenticationError


def build_transient_user(
    *,
    user_id: int,
    email: str,
    display_name: str,
    preferred_name: str | None = None,
    entra_object_id: str | None = None,
) -> ChatbotUser:
    return ChatbotUser(
        id=user_id,
        email=email,
        display_name=display_name,
        preferred_name=preferred_name,
        entra_object_id=entra_object_id,
        is_active=True,
    )


async def get_current_user(
    request: Request,
    x_oneassist_user_id: int | None = Header(default=None),
    authorization: str | None = Header(default=None),
    db_session: AsyncSession | None = Depends(get_db_session),
) -> ChatbotUser:
    settings = get_settings()

    if settings.enable_entra_auth:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=public_auth_message("token_missing"),
            )

        token = authorization.split(" ", 1)[1].strip()
        format_error = token_format_error(token)
        if format_error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=public_auth_message(format_error),
            )
        try:
            identity = get_entra_validator().validate(token)
        except AuthenticationError as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=public_auth_message(error.code),
            ) from error
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=public_auth_message("validation_failed"),
            ) from error

        if not settings.enable_database:
            request.state.auth_roles = identity.roles
            return build_transient_user(
                user_id=x_oneassist_user_id or 0,
                email=identity.email,
                display_name=identity.display_name,
                preferred_name=identity.preferred_name,
                entra_object_id=identity.entra_object_id,
            )

        user = await UserRepository(db_session).upsert_profile(
            display_name=identity.display_name,
            preferred_name=identity.preferred_name,
            email=identity.email,
            employee_id=None,
            department=None,
            job_title=None,
            entra_object_id=identity.entra_object_id,
        )
        request.state.auth_roles = identity.roles
        await db_session.commit()
        await db_session.refresh(user)
        return user

    if x_oneassist_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Initialize the user before calling this endpoint.",
        )

    if not settings.enable_database:
        return build_transient_user(
            user_id=x_oneassist_user_id,
            email="",
            display_name="OneAssist User",
        )

    user = await UserRepository(db_session).get(x_oneassist_user_id)

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current user was not found or is inactive.",
        )

    return user


async def require_admin(
    request: Request,
    x_oneassist_admin: str | None = Header(default=None),
    current_user: ChatbotUser = Depends(get_current_user),
) -> ChatbotUser:
    settings = get_settings()
    roles = set(getattr(request.state, "auth_roles", set()))

    if settings.enable_entra_auth:
        if settings.azure_admin_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin role is required.",
            )
        return current_user

    if str(x_oneassist_admin or "").lower() not in {"1", "true", "yes"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access is required.",
        )

    return current_user
