from functools import lru_cache
import logging
import time
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import get_current_user
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.database import get_db_session
from backend.app.core.existing_database import SessionLocal as ExistingSessionLocal
from backend.app.core.existing_database import get_db as get_existing_db
from backend.app.models.chat_history import ChatbotUser
from backend.app.models.schemas import (
    ChatMessageResponse,
    ChatRequest,
    ChatResponse,
    ChatSessionResponse,
    CreateChatSessionRequest,
    CreateChatSessionResponse,
    PaginatedChatMessagesResponse,
    PaginatedChatSessionsResponse,
)
from backend.app.repositories.existing_postgres import (
    ExistingPostgresRepository,
    persist_chat_best_effort,
    rollback_safely,
)
from backend.app.services.chat_history import ChatHistoryService
from backend.app.services.chatbot import PolicyChatbot

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)


@lru_cache
def get_chatbot() -> PolicyChatbot:
    return PolicyChatbot()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    x_oneassist_user_id: int | None = Header(default=None),
    authorization: str | None = Header(default=None),
    existing_db: Session = Depends(get_existing_db),
) -> ChatResponse:
    if not x_oneassist_user_id:
        started = time.perf_counter()
        response = get_chatbot().answer(
            payload.message,
            user_display_name=payload.resolved_display_name,
            preferred_name=payload.preferred_name,
        )
        response_time_ms = round((time.perf_counter() - started) * 1000)

        return _persist_response_to_existing_db(
            db=existing_db,
            payload=payload,
            response=response,
            response_time_ms=response_time_ms,
        )

    if x_oneassist_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Initialize the user before sending session chat messages.",
        )

    if AsyncSessionLocal is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DATABASE_URL is not configured.",
        )

    async with AsyncSessionLocal() as db_session:
        current_user = await db_session.get(ChatbotUser, x_oneassist_user_id)

        if current_user is None or not current_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Current user was not found or is inactive.",
            )

        started = time.perf_counter()
        response = await ChatHistoryService(
            db_session,
            get_chatbot(),
        ).answer(
            user=current_user,
            session_id=payload.session_id,
            message=payload.message,
            access_token=(
                authorization.split(" ", 1)[1].strip()
                if authorization and authorization.lower().startswith("bearer ")
                else None
            ),
        )
        response_time_ms = round((time.perf_counter() - started) * 1000)

        return _persist_response_to_existing_db(
            db=existing_db,
            payload=payload,
            response=response,
            response_time_ms=response_time_ms,
            fallback_user_email=current_user.email,
            fallback_display_name=current_user.display_name,
            fallback_department=current_user.department,
        )


def _persist_response_to_existing_db(
    *,
    db: Session,
    payload: ChatRequest,
    response: ChatResponse,
    response_time_ms: int,
    fallback_user_email: str | None = None,
    fallback_display_name: str | None = None,
    fallback_department: str | None = None,
) -> ChatResponse:
    logger.info("Existing PostgreSQL save dependency injected: %s", type(db).__name__)
    logger.info("Existing PostgreSQL save starting before response return.")

    try:
        persisted = persist_chat_best_effort(
            db=db,
            message=payload.message,
            response=response,
            response_time_ms=response_time_ms,
            user_email=payload.user_email or fallback_user_email,
            display_name=payload.resolved_display_name or fallback_display_name,
            department=payload.department or fallback_department,
            session_uuid=payload.session_uuid
            or (str(payload.session_id) if payload.session_id else None),
        )
    except SQLAlchemyError as exc:
        rollback_safely(db)
        print(f"SQLAlchemy exception: {type(exc).__name__}")
        logger.exception("Existing PostgreSQL save failed with SQLAlchemy exception: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database save failed. Please try again or contact IT support.",
        ) from exc
    except Exception as exc:
        rollback_safely(db)
        print(f"Database save exception: {type(exc).__name__}")
        logger.exception("Existing PostgreSQL save failed with unexpected exception: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database save failed. Please try again or contact IT support.",
        ) from exc

    logger.info(
        "Existing PostgreSQL save finished before response return: session_id=%s user_message_id=%s assistant_message_id=%s",
        persisted.session_id,
        persisted.user_message_id,
        persisted.assistant_message_id,
    )
    return response.model_copy(
        update={
            "session_id": persisted.session_id,
            "session_uuid": persisted.session_uuid,
            "user_message_id": persisted.user_message_id,
            "assistant_message_id": persisted.assistant_message_id,
        }
    )


@router.post("/chat/sessions", response_model=CreateChatSessionResponse)
async def create_chat_session(
    payload: CreateChatSessionRequest | None = None,
    current_user: ChatbotUser = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
) -> CreateChatSessionResponse:
    chat_session = await ChatHistoryService(
        db_session,
        get_chatbot(),
    ).create_session(
        user=current_user,
        title=payload.title if payload else None,
    )
    return CreateChatSessionResponse(
        session_id=chat_session.id,
        session=chat_session,
    )


@router.get("/chat/sessions")
async def list_chat_sessions(
    user_email: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    if user_email and ExistingSessionLocal is not None:
        with ExistingSessionLocal() as db:
            items = ExistingPostgresRepository(db).list_sessions_for_user(
                user_email=user_email,
            )
            window = items[offset:offset + limit]
            return {
                "items": [_json_safe(item) for item in window],
                "limit": limit,
                "offset": offset,
                "total": len(items),
            }

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="user_email is required for chat history lookup.",
    )


@router.get("/chat/sessions/{session_uuid}")
async def get_chat_session_history(
    session_uuid: str,
    user_email: str | None = Query(default=None),
):
    if not user_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_email is required.",
        )
    if ExistingSessionLocal is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DATABASE_URL is not configured.",
        )

    with ExistingSessionLocal() as db:
        result = ExistingPostgresRepository(db).get_session_with_messages(
            session_uuid=session_uuid,
            user_email=user_email,
        )
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session was not found for this user.",
            )
        return _json_safe(result)


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


@router.get(
    "/chat/sessions/{session_id}/messages",
    response_model=PaginatedChatMessagesResponse,
)
async def list_chat_messages(
    session_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: ChatbotUser = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
) -> PaginatedChatMessagesResponse:
    items, total = await ChatHistoryService(
        db_session,
        get_chatbot(),
    ).list_messages(
        user=current_user,
        session_id=session_id,
        limit=limit,
        offset=offset,
    )
    return PaginatedChatMessagesResponse(
        items=[ChatMessageResponse.model_validate(item) for item in items],
        limit=limit,
        offset=offset,
        total=total,
    )


@router.post(
    "/chat/sessions/{session_id}/end",
    response_model=ChatSessionResponse,
)
async def end_chat_session(
    session_id: UUID,
    current_user: ChatbotUser = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
    existing_db: Session = Depends(get_existing_db),
) -> ChatSessionResponse:
    chat_session = await ChatHistoryService(
        db_session,
        get_chatbot(),
    ).end_session(
        user=current_user,
        session_id=session_id,
    )
    try:
        ExistingPostgresRepository(existing_db).end_session(
            session_uuid=str(session_id),
            user_email=current_user.email,
        )
    except Exception as exc:
        rollback_safely(existing_db)
        logger.exception(
            "Existing PostgreSQL session end failed: session_id=%s error=%s",
            session_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database end-session save failed. Please try again or contact IT support.",
        ) from exc
    return ChatSessionResponse.model_validate(chat_session)
