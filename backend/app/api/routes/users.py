from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import build_transient_user
from backend.app.core.config import get_settings
from backend.app.core.database import get_db_session
from backend.app.models.schemas import (
    UserInitializeRequest,
    UserInitializeResponse,
)
from backend.app.services.chat_history import UserService

router = APIRouter(tags=["users"])


@router.post("/users/initialize", response_model=UserInitializeResponse)
async def initialize_user(
    payload: UserInitializeRequest,
    db_session: AsyncSession | None = Depends(get_db_session),
) -> UserInitializeResponse:
    if not get_settings().enable_database:
        now = datetime.now(UTC)
        user = build_transient_user(
            user_id=0,
            email=str(payload.email),
            display_name=payload.display_name,
            preferred_name=payload.preferred_name,
            entra_object_id=payload.entra_object_id,
        )
        user.employee_id = payload.employee_id
        user.department = payload.department
        user.job_title = payload.job_title
        user.first_seen_at = now
        user.last_seen_at = now
        return UserInitializeResponse(user_id=user.id, profile=user)

    user = await UserService(db_session).initialize_user(payload)
    return UserInitializeResponse(user_id=user.id, profile=user)
