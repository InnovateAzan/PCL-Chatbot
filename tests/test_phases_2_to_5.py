from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.models.chat_history import Base
from backend.app.models.schemas import FeedbackRequest, SourceReference
from backend.app.repositories.chat_history import (
    AnalyticsRepository,
    FeedbackRepository,
    MessageSourceRepository,
    UnansweredQuestionRepository,
)
from backend.app.services.chat_history import ChatHistoryService, UserService
from backend.app.services.chatbot import PolicyChatbot
from backend.app.services.onedesk.intent_service import OneDeskIntentService


def user_payload():
    from backend.app.models.schemas import UserInitializeRequest

    return UserInitializeRequest(
        displayName="Muhammad Azan",
        preferredName="Azan",
        email="azan@example.com",
        employeeId="E-100",
        department="IT",
        jobTitle="Engineer",
        entraObjectId=None,
    )


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )

    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_source_save_feedback_upsert_and_analytics(db_session):
    user = await UserService(db_session).initialize_user(user_payload())
    chat_service = ChatHistoryService(db_session, PolicyChatbot())
    chat_session = await chat_service.create_session(user=user, title=None)
    response = await chat_service.answer(
        user=user,
        session_id=chat_session.id,
        message="hi",
    )

    sources = await MessageSourceRepository(db_session).save_sources(
        assistant_message_id=response.assistant_message_id,
        sources=[
            SourceReference(
                document_name="Policy.docx",
                section="Security",
                page_number=2,
                chunk_id="chunk-1",
                similarity_score=0.91,
            )
        ],
    )
    feedback_repo = FeedbackRepository(db_session)
    feedback = await feedback_repo.upsert(
        assistant_message_id=response.assistant_message_id,
        user_id=user.id,
        rating=5,
        feedback_type="HELPFUL",
        comments="Good",
    )
    updated = await feedback_repo.upsert(
        assistant_message_id=response.assistant_message_id,
        user_id=user.id,
        rating=4,
        feedback_type="HELPFUL",
        comments="Still good",
    )
    await db_session.commit()

    summary = await AnalyticsRepository(db_session).summary()

    assert sources[0].document_name == "Policy.docx"
    assert feedback.id == updated.id
    assert updated.rating == 4
    assert summary["feedback_count"] == 1
    assert summary["total_user_questions"] == 1


@pytest.mark.asyncio
async def test_unanswered_question_occurrence_increment(db_session):
    user = await UserService(db_session).initialize_user(user_payload())
    chat_service = ChatHistoryService(db_session, PolicyChatbot())
    chat_session = await chat_service.create_session(user=user, title=None)
    response = await chat_service.answer(
        user=user,
        session_id=chat_session.id,
        message="hi",
    )
    repo = UnansweredQuestionRepository(db_session)

    first = await repo.upsert_occurrence(
        user_message_id=response.user_message_id,
        normalized_question="unknown thing",
        detected_topic="Security",
    )
    second = await repo.upsert_occurrence(
        user_message_id=response.user_message_id,
        normalized_question="unknown thing",
        detected_topic="Security",
    )

    assert first.id == second.id
    assert second.occurrence_count == 2


def test_feedback_rating_validation_and_onedesk_intent_detection():
    with pytest.raises(ValidationError):
        FeedbackRequest(rating=6, feedbackType="HELPFUL")

    intent = OneDeskIntentService().detect("What is the status of ticket IT-1025?")

    assert intent.intent_type == "IT_TICKET_STATUS"
    assert intent.module == "it"
    assert intent.request_number == "IT-1025"
