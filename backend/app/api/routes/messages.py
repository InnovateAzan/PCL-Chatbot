from fastapi import APIRouter, Depends
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_user
from backend.app.core.database import get_db_session
from backend.app.core.existing_database import SessionLocal as ExistingSessionLocal
from backend.app.models.chat_history import ChatbotUser
from backend.app.models.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    LegacyFeedbackRequest,
    LegacyFeedbackResponse,
    MessageSourceResponse,
    MessageSourcesResponse,
)
from backend.app.repositories.existing_postgres import ExistingPostgresRepository
from backend.app.services.chat_history import FeedbackService

router = APIRouter(tags=["messages"])


@router.post("/feedback", response_model=LegacyFeedbackResponse)
def submit_legacy_feedback(payload: LegacyFeedbackRequest) -> LegacyFeedbackResponse:
    if ExistingSessionLocal is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DATABASE_URL is not configured.",
        )

    with ExistingSessionLocal() as db:
        try:
            row = ExistingPostgresRepository(db).save_feedback(
                message_id=payload.message_id,
                rating=payload.rating,
                comments=payload.comments,
                user_email=payload.user_email,
            )
            db.commit()
        except ValueError as error:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(error),
            ) from error
        except Exception as error:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Feedback could not be saved.",
            ) from error

    return LegacyFeedbackResponse(
        id=row.get("id"),
        messageId=payload.message_id,
        rating=payload.rating,
        saved=True,
    )


@router.post("/messages/{message_id}/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    message_id: int,
    payload: FeedbackRequest,
    current_user: ChatbotUser = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
) -> FeedbackResponse:
    feedback = await FeedbackService(db_session).submit_feedback(
        user=current_user,
        assistant_message_id=message_id,
        payload=payload,
    )
    return FeedbackResponse.model_validate(feedback)


@router.get("/messages/{message_id}/sources", response_model=MessageSourcesResponse)
async def list_message_sources(
    message_id: int,
    current_user: ChatbotUser = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
) -> MessageSourcesResponse:
    sources = await FeedbackService(db_session).list_sources(
        user=current_user,
        assistant_message_id=message_id,
    )
    return MessageSourcesResponse(
        items=[MessageSourceResponse.model_validate(source) for source in sources]
    )
