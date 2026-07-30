from __future__ import annotations

import time
import re
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.models.chat_history import (
    ChatMessage,
    ChatSession,
    ChatbotUser,
    MessageFeedback,
    MessageSource,
    UnansweredQuestion,
)
from backend.app.models.schemas import (
    ChatResponse,
    FeedbackRequest,
    UpdateUnansweredQuestionRequest,
    UserInitializeRequest,
)
from backend.app.repositories.chat_history import (
    AnalyticsRepository,
    AuditLogRepository,
    ChatMessageRepository,
    ChatSessionRepository,
    FeedbackRepository,
    MessageSourceRepository,
    UnansweredQuestionRepository,
    UserRepository,
)
from backend.app.services.chatbot import PolicyChatbot
from backend.app.services.onedesk.ticket_service import OneDeskService


class UserService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session
        self.users = UserRepository(db_session)

    async def initialize_user(self, payload: UserInitializeRequest) -> ChatbotUser:
        try:
            user = await self.users.upsert_profile(
                display_name=payload.display_name,
                preferred_name=payload.preferred_name,
                email=str(payload.email).lower(),
                employee_id=payload.employee_id,
                department=payload.department,
                job_title=payload.job_title,
                entra_object_id=payload.entra_object_id,
            )
            await self.db_session.commit()
            await self.db_session.refresh(user)
            return user
        except IntegrityError as error:
            await self.db_session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email or Entra object ID already exists.",
            ) from error


class ChatHistoryService:
    def __init__(
        self,
        db_session: AsyncSession,
        chatbot: PolicyChatbot,
    ) -> None:
        self.db_session = db_session
        self.chatbot = chatbot
        self.onedesk = OneDeskService()
        self.settings = get_settings()
        self.sessions = ChatSessionRepository(db_session)
        self.messages = ChatMessageRepository(db_session)
        self.sources = MessageSourceRepository(db_session)
        self.unanswered = UnansweredQuestionRepository(db_session)
        self.audit = AuditLogRepository(db_session)

    async def create_session(
        self,
        *,
        user: ChatbotUser,
        title: str | None,
    ) -> ChatSession:
        chat_session = await self.sessions.create(user_id=user.id, title=title)
        await self.db_session.commit()
        await self.db_session.refresh(chat_session)
        return chat_session

    async def answer(
        self,
        *,
        user: ChatbotUser,
        session_id: UUID,
        message: str,
        access_token: str | None = None,
    ) -> ChatResponse:
        chat_session = await self.sessions.get_owned(
            session_id=session_id,
            user_id=user.id,
        )

        if chat_session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session was not found for the current user.",
            )

        if chat_session.status != "ACTIVE":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Chat session has already ended.",
            )

        started = time.perf_counter()
        user_message = await self.messages.create(
            session_id=chat_session.id,
            user_id=user.id,
            role="USER",
            message_text=message.strip(),
        )

        if self.onedesk.should_handle(message):
            response = await self.onedesk.answer(
                message=message,
                user_email=user.email,
                access_token=access_token,
            )
            await self.audit.create(
                user_id=user.id,
                action="ONEDESK_QUERY",
                resource_type="chat_session",
                resource_id=str(session_id),
                result="SUCCESS",
                ip_address=None,
                user_agent=None,
                metadata_json={"provider": response.provider},
            )
        else:
            response = self.chatbot.answer(
                message,
                user_display_name=user.display_name,
                preferred_name=user.preferred_name,
            )
        response_time_ms = round((time.perf_counter() - started) * 1000)
        response_source = self._map_response_source(response)
        model_name = self._resolve_model_name(response)

        assistant_message = await self.messages.create(
            session_id=chat_session.id,
            user_id=user.id,
            role="ASSISTANT",
            message_text=response.answer,
            response_source=response_source,
            model_name=model_name,
            response_time_ms=response_time_ms,
            fallback_used=response.fallback,
            metadata_json={
                "provider": response.provider,
                "notice": response.notice,
                "source_count": len(response.sources),
            },
        )
        await self.sources.save_sources(
            assistant_message_id=assistant_message.id,
            sources=response.sources,
        )

        if self._is_unanswered(message=message, response=response):
            await self.unanswered.upsert_occurrence(
                user_message_id=user_message.id,
                normalized_question=self._normalize_question(message),
                detected_topic=self._detect_topic(message),
            )

        await self.sessions.increment_message_count(chat_session, by=2)

        await self.db_session.commit()

        return response.model_copy(
            update={
                "user_message_id": user_message.id,
                "assistant_message_id": assistant_message.id,
                "response_source": response_source,
            }
        )

    async def list_sessions(
        self,
        *,
        user: ChatbotUser,
        limit: int,
        offset: int,
    ) -> tuple[list[ChatSession], int]:
        return await self.sessions.list_owned(
            user_id=user.id,
            limit=limit,
            offset=offset,
        )

    async def list_messages(
        self,
        *,
        user: ChatbotUser,
        session_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[ChatMessage], int]:
        chat_session = await self.sessions.get_owned(
            session_id=session_id,
            user_id=user.id,
        )

        if chat_session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session was not found for the current user.",
            )

        return await self.messages.list_owned_for_session(
            session_id=session_id,
            user_id=user.id,
            limit=limit,
            offset=offset,
        )

    async def end_session(
        self,
        *,
        user: ChatbotUser,
        session_id: UUID,
    ) -> ChatSession:
        chat_session = await self.sessions.get_owned(
            session_id=session_id,
            user_id=user.id,
        )

        if chat_session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session was not found for the current user.",
            )

        if chat_session.status != "ENDED":
            await self.sessions.end(chat_session)
            await self.db_session.commit()
            await self.db_session.refresh(chat_session)

        return chat_session

    def _resolve_model_name(self, response: ChatResponse) -> str | None:
        if response.provider.startswith("gemini"):
            return self.settings.gemini_model

        return None

    @staticmethod
    def _map_response_source(response: ChatResponse) -> str:
        provider = response.provider.lower()

        if "greeting" in provider:
            return "GREETING"

        if response.fallback:
            return "FALLBACK"

        if "general" in provider:
            return "GENERAL_AI"

        if "onedesk" in provider:
            return "ONEDESK"

        if "policy" in provider:
            return "POLICY"

        return "FALLBACK"

    def _is_unanswered(self, *, message: str, response: ChatResponse) -> bool:
        if response.fallback:
            return True

        answer = response.answer.lower()
        if "information not available" in answer or "not covered" in answer:
            return True

        if not response.sources and response.response_source != "GREETING":
            return response.provider != "local-greeting"

        threshold = self.settings.policy_relevance_threshold
        scores = [
            source.similarity_score
            for source in response.sources
            if source.similarity_score is not None
        ]
        return bool(scores) and max(scores) < threshold

    @staticmethod
    def _normalize_question(message: str) -> str:
        normalized = message.lower().strip()
        normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized[:1000]

    @staticmethod
    def _detect_topic(message: str) -> str | None:
        normalized = message.lower()
        topics = {
            "Access Control": ("access", "password", "mfa", "identity"),
            "Procurement": ("hardware", "software", "procurement", "purchase"),
            "Security": ("security", "cyber", "incident", "risk"),
            "Backup": ("backup", "restore", "disaster"),
            "OneDesk": ("ticket", "request", "approval", "fleet", "facility", "qc"),
        }

        for topic, keywords in topics.items():
            if any(keyword in normalized for keyword in keywords):
                return topic

        return None


class FeedbackService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session
        self.messages = ChatMessageRepository(db_session)
        self.feedback = FeedbackRepository(db_session)
        self.sources = MessageSourceRepository(db_session)

    async def submit_feedback(
        self,
        *,
        user: ChatbotUser,
        assistant_message_id: int,
        payload: FeedbackRequest,
    ) -> MessageFeedback:
        message = await self.messages.get_owned_assistant_message(
            message_id=assistant_message_id,
            user_id=user.id,
        )

        if message is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assistant message was not found for the current user.",
            )

        feedback = await self.feedback.upsert(
            assistant_message_id=assistant_message_id,
            user_id=user.id,
            rating=payload.rating,
            feedback_type=payload.feedback_type,
            comments=payload.comments,
        )
        await self.db_session.commit()
        await self.db_session.refresh(feedback)
        return feedback

    async def list_sources(
        self,
        *,
        user: ChatbotUser,
        assistant_message_id: int,
    ) -> list[MessageSource]:
        return await self.sources.list_for_owned_message(
            assistant_message_id=assistant_message_id,
            user_id=user.id,
        )


class AdminService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session
        self.unanswered = UnansweredQuestionRepository(db_session)
        self.analytics = AnalyticsRepository(db_session)

    async def list_unanswered(
        self,
        *,
        limit: int,
        offset: int,
        review_status: str | None,
    ) -> tuple[list[UnansweredQuestion], int]:
        return await self.unanswered.list(
            limit=limit,
            offset=offset,
            review_status=review_status,
        )

    async def update_unanswered(
        self,
        *,
        item_id: int,
        payload: UpdateUnansweredQuestionRequest,
    ) -> UnansweredQuestion:
        item = await self.unanswered.update(
            item_id=item_id,
            review_status=payload.review_status,
            reviewed_by=payload.reviewed_by,
            improvement_notes=payload.improvement_notes,
        )

        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Unanswered question was not found.",
            )

        await self.db_session.commit()
        await self.db_session.refresh(item)
        return item

    async def analytics_summary(self) -> dict:
        return await self.analytics.summary()
