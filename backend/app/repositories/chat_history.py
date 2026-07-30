from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.chat_history import (
    AuditLog,
    ChatMessage,
    ChatSession,
    ChatbotUser,
    MessageFeedback,
    MessageSource,
    UnansweredQuestion,
)
from backend.app.models.schemas import SourceReference


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_by_identity(
        self,
        *,
        email: str,
        entra_object_id: str | None,
    ) -> ChatbotUser | None:
        filters = [ChatbotUser.email == email]

        if entra_object_id:
            filters.append(ChatbotUser.entra_object_id == entra_object_id)

        result = await self.session.execute(
            select(ChatbotUser).where(or_(*filters)).limit(1)
        )
        return result.scalar_one_or_none()

    async def get(self, user_id: int) -> ChatbotUser | None:
        return await self.session.get(ChatbotUser, user_id)

    async def upsert_profile(
        self,
        *,
        display_name: str,
        preferred_name: str | None,
        email: str,
        employee_id: str | None,
        department: str | None,
        job_title: str | None,
        entra_object_id: str | None,
    ) -> ChatbotUser:
        now = datetime.now(UTC)
        user = await self.find_by_identity(
            email=email,
            entra_object_id=entra_object_id,
        )

        if user is None:
            user = ChatbotUser(
                display_name=display_name,
                preferred_name=preferred_name,
                email=email,
                employee_id=employee_id,
                department=department,
                job_title=job_title,
                entra_object_id=entra_object_id,
                first_seen_at=now,
                last_seen_at=now,
            )
            self.session.add(user)
            await self.session.flush()
            return user

        user.display_name = display_name
        user.preferred_name = preferred_name
        user.employee_id = employee_id
        user.department = department
        user.job_title = job_title
        user.last_seen_at = now

        if entra_object_id and user.entra_object_id != entra_object_id:
            user.entra_object_id = entra_object_id

        await self.session.flush()
        return user


class ChatSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, user_id: int, title: str | None = None) -> ChatSession:
        chat_session = ChatSession(user_id=user_id, title=title)
        self.session.add(chat_session)
        await self.session.flush()
        return chat_session

    async def get_owned(
        self,
        *,
        session_id: UUID,
        user_id: int,
    ) -> ChatSession | None:
        result = await self.session.execute(
            select(ChatSession)
            .where(
                ChatSession.id == session_id,
                ChatSession.user_id == user_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_owned(
        self,
        *,
        user_id: int,
        limit: int,
        offset: int,
    ) -> tuple[list[ChatSession], int]:
        total_result = await self.session.execute(
            select(func.count())
            .select_from(ChatSession)
            .where(ChatSession.user_id == user_id)
        )
        total = int(total_result.scalar_one())

        rows = await self.session.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().all()), total

    async def end(self, chat_session: ChatSession) -> ChatSession:
        chat_session.status = "ENDED"
        chat_session.ended_at = datetime.now(UTC)
        await self.session.flush()
        return chat_session

    async def increment_message_count(
        self,
        chat_session: ChatSession,
        *,
        by: int,
    ) -> None:
        chat_session.message_count += by
        await self.session.flush()


class ChatMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        session_id: UUID,
        user_id: int,
        role: str,
        message_text: str,
        response_source: str | None = None,
        model_name: str | None = None,
        response_time_ms: int | None = None,
        fallback_used: bool = False,
        metadata_json: dict | None = None,
    ) -> ChatMessage:
        message = ChatMessage(
            session_id=session_id,
            user_id=user_id,
            role=role,
            message_text=message_text,
            response_source=response_source,
            model_name=model_name,
            response_time_ms=response_time_ms,
            fallback_used=fallback_used,
            metadata_json=metadata_json,
        )
        self.session.add(message)
        await self.session.flush()
        return message

    async def list_owned_for_session(
        self,
        *,
        session_id: UUID,
        user_id: int,
        limit: int,
        offset: int,
    ) -> tuple[list[ChatMessage], int]:
        ownership_query = select(ChatSession.id).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        )

        total_result = await self.session.execute(
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.session_id.in_(ownership_query))
        )
        total = int(total_result.scalar_one())

        rows = await self.session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id.in_(ownership_query))
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().all()), total

    async def get_owned_assistant_message(
        self,
        *,
        message_id: int,
        user_id: int,
    ) -> ChatMessage | None:
        result = await self.session.execute(
            select(ChatMessage)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .where(
                ChatMessage.id == message_id,
                ChatMessage.role == "ASSISTANT",
                ChatSession.user_id == user_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()


class MessageSourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_sources(
        self,
        *,
        assistant_message_id: int,
        sources: list[SourceReference],
    ) -> list[MessageSource]:
        rows: list[MessageSource] = []

        for index, source in enumerate(sources, start=1):
            row = MessageSource(
                assistant_message_id=assistant_message_id,
                document_name=source.document_name,
                section_name=source.section,
                page_number=source.page_number,
                chunk_id=source.chunk_id,
                similarity_score=source.similarity_score,
                source_order=index,
            )
            self.session.add(row)
            rows.append(row)

        await self.session.flush()
        return rows

    async def list_for_owned_message(
        self,
        *,
        assistant_message_id: int,
        user_id: int,
    ) -> list[MessageSource]:
        result = await self.session.execute(
            select(MessageSource)
            .join(ChatMessage, ChatMessage.id == MessageSource.assistant_message_id)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .where(
                MessageSource.assistant_message_id == assistant_message_id,
                ChatSession.user_id == user_id,
            )
            .order_by(MessageSource.source_order.asc())
        )
        return list(result.scalars().all())


class FeedbackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(
        self,
        *,
        assistant_message_id: int,
        user_id: int,
        rating: int | None,
        feedback_type: str,
        comments: str | None,
    ) -> MessageFeedback:
        result = await self.session.execute(
            select(MessageFeedback)
            .where(
                MessageFeedback.assistant_message_id == assistant_message_id,
                MessageFeedback.user_id == user_id,
            )
            .limit(1)
        )
        feedback = result.scalar_one_or_none()

        if feedback is None:
            feedback = MessageFeedback(
                assistant_message_id=assistant_message_id,
                user_id=user_id,
                rating=rating,
                feedback_type=feedback_type,
                comments=comments,
            )
            self.session.add(feedback)
        else:
            feedback.rating = rating
            feedback.feedback_type = feedback_type
            feedback.comments = comments

        await self.session.flush()
        return feedback


class UnansweredQuestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_occurrence(
        self,
        *,
        user_message_id: int,
        normalized_question: str,
        detected_topic: str | None,
    ) -> UnansweredQuestion:
        result = await self.session.execute(
            select(UnansweredQuestion)
            .where(UnansweredQuestion.normalized_question == normalized_question)
            .limit(1)
        )
        item = result.scalar_one_or_none()

        if item is None:
            item = UnansweredQuestion(
                user_message_id=user_message_id,
                normalized_question=normalized_question,
                detected_topic=detected_topic,
            )
            self.session.add(item)
        else:
            item.occurrence_count += 1
            if detected_topic and not item.detected_topic:
                item.detected_topic = detected_topic

        await self.session.flush()
        return item

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        review_status: str | None = None,
    ) -> tuple[list[UnansweredQuestion], int]:
        filters = []
        if review_status:
            filters.append(UnansweredQuestion.review_status == review_status)

        total_result = await self.session.execute(
            select(func.count()).select_from(UnansweredQuestion).where(*filters)
        )
        total = int(total_result.scalar_one())

        rows = await self.session.execute(
            select(UnansweredQuestion)
            .where(*filters)
            .order_by(UnansweredQuestion.occurrence_count.desc(), UnansweredQuestion.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().all()), total

    async def update(
        self,
        *,
        item_id: int,
        review_status: str | None,
        reviewed_by: str | None,
        improvement_notes: str | None,
    ) -> UnansweredQuestion | None:
        item = await self.session.get(UnansweredQuestion, item_id)
        if item is None:
            return None

        if review_status:
            item.review_status = review_status
            item.reviewed_at = datetime.now(UTC)
        if reviewed_by is not None:
            item.reviewed_by = reviewed_by
        if improvement_notes is not None:
            item.improvement_notes = improvement_notes

        await self.session.flush()
        return item


class AuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: int | None,
        action: str,
        resource_type: str,
        resource_id: str | None,
        result: str,
        ip_address: str | None,
        user_agent: str | None,
        metadata_json: dict | None = None,
    ) -> AuditLog:
        row = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata_json=metadata_json,
        )
        self.session.add(row)
        await self.session.flush()
        return row


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def summary(self) -> dict[str, int | float | None]:
        counts = {}
        counts["total_users"] = await self._count(ChatbotUser)
        counts["active_users"] = await self._scalar(
            select(func.count()).select_from(ChatbotUser).where(ChatbotUser.is_active.is_(True))
        )
        counts["total_chat_sessions"] = await self._count(ChatSession)
        counts["total_user_questions"] = await self._scalar(
            select(func.count()).select_from(ChatMessage).where(ChatMessage.role == "USER")
        )
        counts["total_assistant_responses"] = await self._scalar(
            select(func.count()).select_from(ChatMessage).where(ChatMessage.role == "ASSISTANT")
        )

        for source in ["POLICY", "GENERAL_AI", "ONEDESK", "FALLBACK"]:
            counts[f"{source.lower()}_responses"] = await self._scalar(
                select(func.count())
                .select_from(ChatMessage)
                .where(
                    ChatMessage.role == "ASSISTANT",
                    ChatMessage.response_source == source,
                )
            )

        counts["unanswered_questions"] = await self._count(UnansweredQuestion)
        counts["feedback_count"] = await self._count(MessageFeedback)
        counts["average_feedback_rating"] = await self._scalar(
            select(func.avg(MessageFeedback.rating)).where(MessageFeedback.rating.is_not(None))
        )
        helpful_count = await self._scalar(
            select(func.count()).select_from(MessageFeedback).where(MessageFeedback.feedback_type == "HELPFUL")
        )
        feedback_count = int(counts["feedback_count"] or 0)
        counts["helpful_percentage"] = (
            round((helpful_count / feedback_count) * 100, 2)
            if feedback_count
            else None
        )
        counts["average_response_time_ms"] = await self._scalar(
            select(func.avg(ChatMessage.response_time_ms)).where(
                ChatMessage.role == "ASSISTANT",
                ChatMessage.response_time_ms.is_not(None),
            )
        )
        return counts

    async def usage_by_day(self, *, limit: int = 31) -> list[dict]:
        day = func.date(ChatMessage.created_at)
        rows = await self.session.execute(
            select(day.label("label"), func.count().label("value"))
            .where(ChatMessage.role == "USER")
            .group_by(day)
            .order_by(desc(day))
            .limit(limit)
        )
        return [{"label": str(label), "value": int(value)} for label, value in rows.all()]

    async def top_questions(self, *, limit: int = 20) -> list[dict]:
        normalized = func.lower(func.trim(ChatMessage.message_text))
        rows = await self.session.execute(
            select(normalized.label("question"), func.count().label("count"))
            .where(ChatMessage.role == "USER")
            .group_by(normalized)
            .order_by(desc("count"))
            .limit(limit)
        )
        return [{"question": question, "count": int(count)} for question, count in rows.all()]

    async def top_policies(self, *, limit: int = 20) -> list[dict]:
        rows = await self.session.execute(
            select(MessageSource.document_name, func.count().label("count"))
            .group_by(MessageSource.document_name)
            .order_by(desc("count"))
            .limit(limit)
        )
        return [{"documentName": name, "count": int(count)} for name, count in rows.all()]

    async def feedback(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        total = await self._count(MessageFeedback)
        rows = await self.session.execute(
            select(
                MessageFeedback.id,
                MessageFeedback.rating,
                MessageFeedback.feedback_type,
                MessageFeedback.comments,
                MessageFeedback.created_at,
            )
            .order_by(MessageFeedback.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [
            {
                "id": row.id,
                "rating": row.rating,
                "feedbackType": row.feedback_type,
                "comments": row.comments,
                "createdAt": row.created_at.isoformat(),
            }
            for row in rows.all()
        ], total

    async def unanswered_topics(self, *, limit: int = 20) -> list[dict]:
        topic = func.coalesce(UnansweredQuestion.detected_topic, "Uncategorized")
        rows = await self.session.execute(
            select(topic.label("topic"), func.sum(UnansweredQuestion.occurrence_count).label("count"))
            .group_by(topic)
            .order_by(desc("count"))
            .limit(limit)
        )
        return [{"topic": topic_value, "count": int(count)} for topic_value, count in rows.all()]

    async def _count(self, model: type) -> int:
        return int(await self._scalar(select(func.count()).select_from(model)) or 0)

    async def _scalar(self, statement):
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()
