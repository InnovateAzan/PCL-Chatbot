from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.dependencies import require_admin
from backend.app.core.database import get_db_session
from backend.app.models.chat_history import ChatbotUser
from backend.app.models.schemas import (
    AnalyticsListResponse,
    AnalyticsSummaryResponse,
    PaginatedUnansweredQuestionsResponse,
    UnansweredQuestionResponse,
    UpdateUnansweredQuestionRequest,
)
from backend.app.repositories.chat_history import AnalyticsRepository
from backend.app.services.chat_history import AdminService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/unanswered-questions", response_model=PaginatedUnansweredQuestionsResponse)
async def list_unanswered_questions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    review_status: str | None = Query(default=None, alias="reviewStatus"),
    _: ChatbotUser = Depends(require_admin),
    db_session: AsyncSession = Depends(get_db_session),
) -> PaginatedUnansweredQuestionsResponse:
    items, total = await AdminService(db_session).list_unanswered(
        limit=limit,
        offset=offset,
        review_status=review_status.upper() if review_status else None,
    )
    return PaginatedUnansweredQuestionsResponse(
        items=[UnansweredQuestionResponse.model_validate(item) for item in items],
        limit=limit,
        offset=offset,
        total=total,
    )


@router.patch(
    "/unanswered-questions/{item_id}",
    response_model=UnansweredQuestionResponse,
)
async def update_unanswered_question(
    item_id: int,
    payload: UpdateUnansweredQuestionRequest,
    _: ChatbotUser = Depends(require_admin),
    db_session: AsyncSession = Depends(get_db_session),
) -> UnansweredQuestionResponse:
    item = await AdminService(db_session).update_unanswered(
        item_id=item_id,
        payload=payload,
    )
    return UnansweredQuestionResponse.model_validate(item)


@router.get("/analytics/summary", response_model=AnalyticsSummaryResponse)
async def analytics_summary(
    _: ChatbotUser = Depends(require_admin),
    db_session: AsyncSession = Depends(get_db_session),
) -> AnalyticsSummaryResponse:
    payload = await AnalyticsRepository(db_session).summary()
    return AnalyticsSummaryResponse(
        totalUsers=int(payload["total_users"] or 0),
        activeUsers=int(payload["active_users"] or 0),
        totalChatSessions=int(payload["total_chat_sessions"] or 0),
        totalUserQuestions=int(payload["total_user_questions"] or 0),
        totalAssistantResponses=int(payload["total_assistant_responses"] or 0),
        policyBasedResponses=int(payload["policy_responses"] or 0),
        generalAiResponses=int(payload["general_ai_responses"] or 0),
        onedeskLiveDataResponses=int(payload["onedesk_responses"] or 0),
        fallbackResponses=int(payload["fallback_responses"] or 0),
        unansweredQuestions=int(payload["unanswered_questions"] or 0),
        feedbackCount=int(payload["feedback_count"] or 0),
        averageFeedbackRating=payload["average_feedback_rating"],
        helpfulPercentage=payload["helpful_percentage"],
        averageResponseTimeMs=payload["average_response_time_ms"],
    )


@router.get("/analytics/usage", response_model=AnalyticsListResponse)
async def analytics_usage(
    _: ChatbotUser = Depends(require_admin),
    db_session: AsyncSession = Depends(get_db_session),
) -> AnalyticsListResponse:
    return AnalyticsListResponse(items=await AnalyticsRepository(db_session).usage_by_day())


@router.get("/analytics/top-questions", response_model=AnalyticsListResponse)
async def analytics_top_questions(
    limit: int = Query(default=20, ge=1, le=100),
    _: ChatbotUser = Depends(require_admin),
    db_session: AsyncSession = Depends(get_db_session),
) -> AnalyticsListResponse:
    return AnalyticsListResponse(
        items=await AnalyticsRepository(db_session).top_questions(limit=limit)
    )


@router.get("/analytics/top-policies", response_model=AnalyticsListResponse)
async def analytics_top_policies(
    limit: int = Query(default=20, ge=1, le=100),
    _: ChatbotUser = Depends(require_admin),
    db_session: AsyncSession = Depends(get_db_session),
) -> AnalyticsListResponse:
    return AnalyticsListResponse(
        items=await AnalyticsRepository(db_session).top_policies(limit=limit)
    )


@router.get("/analytics/feedback", response_model=AnalyticsListResponse)
async def analytics_feedback(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: ChatbotUser = Depends(require_admin),
    db_session: AsyncSession = Depends(get_db_session),
) -> AnalyticsListResponse:
    items, total = await AnalyticsRepository(db_session).feedback(
        limit=limit,
        offset=offset,
    )
    return AnalyticsListResponse(items=items, limit=limit, offset=offset, total=total)


@router.get("/analytics/unanswered-topics", response_model=AnalyticsListResponse)
async def analytics_unanswered_topics(
    _: ChatbotUser = Depends(require_admin),
    db_session: AsyncSession = Depends(get_db_session),
) -> AnalyticsListResponse:
    return AnalyticsListResponse(
        items=await AnalyticsRepository(db_session).unanswered_topics()
    )
