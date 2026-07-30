from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

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
    db_session: AsyncSession = Depends(get_db_session),
) -> UserInitializeResponse:
    user = await UserService(db_session).initialize_user(payload)
    return UserInitializeResponse(user_id=user.id, profile=user)
