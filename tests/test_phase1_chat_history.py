from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.models.chat_history import Base
from backend.app.models.schemas import UserInitializeRequest
from backend.app.models.schemas import ChatResponse, SourceReference
from backend.app.services.chat_history import ChatHistoryService, UserService
from backend.app.services.chatbot import PolicyChatbot


@pytest.fixture
async def db_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )

    yield factory
    await engine.dispose()


@pytest.fixture
async def db_session(db_session_factory):
    async with db_session_factory() as session:
        yield session


def user_payload(
    *,
    email: str = "azan@example.com",
    display_name: str = "Muhammad Azan",
    preferred_name: str | None = "Azan",
) -> UserInitializeRequest:
    return UserInitializeRequest(
        displayName=display_name,
        preferredName=preferred_name,
        email=email,
        employeeId="E-100",
        department="IT",
        jobTitle="Engineer",
        entraObjectId=None,
    )


@pytest.mark.asyncio
async def test_user_create_update_and_duplicate_email_prevention(db_session):
    service = UserService(db_session)

    first = await service.initialize_user(user_payload())
    second = await service.initialize_user(
        user_payload(display_name="Muhammad Azan Khan", preferred_name="Azan")
    )

    assert second.id == first.id
    assert second.email == "azan@example.com"
    assert second.display_name == "Muhammad Azan Khan"


@pytest.mark.asyncio
async def test_session_ownership_and_session_end(db_session):
    first_user = await UserService(db_session).initialize_user(user_payload())
    second_user = await UserService(db_session).initialize_user(
        user_payload(email="other@example.com", display_name="Other User")
    )
    service = ChatHistoryService(db_session, PolicyChatbot())

    chat_session = await service.create_session(user=first_user, title=None)

    with pytest.raises(HTTPException):
        await service.list_messages(
            user=second_user,
            session_id=chat_session.id,
            limit=20,
            offset=0,
        )

    ended = await service.end_session(user=first_user, session_id=chat_session.id)
    assert ended.status == "ENDED"
    assert ended.ended_at is not None


@pytest.mark.asyncio
async def test_message_save_assistant_response_save_and_personalized_greeting(
    db_session,
):
    user = await UserService(db_session).initialize_user(user_payload())
    service = ChatHistoryService(db_session, PolicyChatbot())
    chat_session = await service.create_session(user=user, title=None)

    response = await service.answer(
        user=user,
        session_id=chat_session.id,
        message="hi",
    )
    messages, total = await service.list_messages(
        user=user,
        session_id=chat_session.id,
        limit=20,
        offset=0,
    )

    assert response.answer == "Hi Azan, how can I help you today?"
    assert response.response_source == "GREETING"
    assert response.user_message_id is not None
    assert response.assistant_message_id is not None
    assert total == 2
    assert [message.role for message in messages] == ["USER", "ASSISTANT"]
    assert messages[1].message_text == response.answer


@pytest.mark.asyncio
async def test_session_policy_context_is_passed_to_follow_up(db_session):
    class ContextAwareChatbot(PolicyChatbot):
        def __init__(self):
            self.seen_contexts = []

        def answer(
            self,
            message,
            user_display_name=None,
            preferred_name=None,
            active_policy_context=None,
        ):
            self.seen_contexts.append(active_policy_context)
            document_number = (
                active_policy_context.get("document_number")
                if active_policy_context
                else "0040"
            )
            return ChatResponse(
                answer="Policy answer",
                sources=[
                    SourceReference(
                        document_name=(
                            "0040 - PCL - AI Governance Policy.pdf"
                        ),
                        document_number=document_number,
                        title="PCL - AI Governance Policy",
                        page_number=1,
                        relevance_score=0.9,
                    )
                ],
                provider="policy-rules",
                active_policy_context={
                    "document_number": document_number,
                    "title": "PCL - AI Governance Policy",
                    "document_name": (
                        "0040 - PCL - AI Governance Policy.pdf"
                    ),
                    "keywords": ["AI Governance"],
                    "pages": [1],
                    "last_question": message,
                },
            )

    user = await UserService(db_session).initialize_user(user_payload())
    chatbot = ContextAwareChatbot()
    service = ChatHistoryService(db_session, chatbot)
    chat_session = await service.create_session(user=user, title=None)

    await service.answer(
        user=user,
        session_id=chat_session.id,
        message="What is AI Governance?",
    )
    await service.answer(
        user=user,
        session_id=chat_session.id,
        message="How can I implement it?",
    )

    assert chatbot.seen_contexts[0] is None
    assert chatbot.seen_contexts[1]["document_number"] == "0040"
