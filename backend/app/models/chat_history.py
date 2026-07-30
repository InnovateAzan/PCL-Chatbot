from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


BIGINT_ID = BigInteger().with_variant(Integer, "sqlite")


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ChatbotUser(TimestampMixin, Base):
    __tablename__ = "chatbot_users"

    id: Mapped[int] = mapped_column(
        BIGINT_ID,
        Identity(always=False),
        primary_key=True,
    )
    entra_object_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employee_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    preferred_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="true",
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    sessions: Mapped[list[ChatSession]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    messages: Mapped[list[ChatMessage]] = relationship(back_populates="user")

    __table_args__ = (
        UniqueConstraint("email", name="uq_chatbot_users_email"),
        UniqueConstraint("entra_object_id", name="uq_chatbot_users_entra_object_id"),
        Index("ix_chatbot_users_email", "email"),
    )


class ChatSession(TimestampMixin, Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("chatbot_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="ACTIVE",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    message_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )

    user: Mapped[ChatbotUser] = relationship(back_populates="sessions")
    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'ENDED')",
            name="ck_chat_sessions_status",
        ),
        Index("ix_chat_sessions_user_id", "user_id"),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(
        BIGINT_ID,
        Identity(always=False),
        primary_key=True,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("chatbot_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fallback_used: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    metadata_json: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )

    session: Mapped[ChatSession] = relationship(back_populates="messages")
    user: Mapped[ChatbotUser] = relationship(back_populates="messages")
    sources: Mapped[list[MessageSource]] = relationship(
        back_populates="assistant_message",
        cascade="all, delete-orphan",
    )
    feedback_items: Mapped[list[MessageFeedback]] = relationship(
        back_populates="assistant_message",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('USER', 'ASSISTANT', 'SYSTEM')",
            name="ck_chat_messages_role",
        ),
        CheckConstraint(
            "response_source IS NULL OR response_source IN "
            "('POLICY', 'GENERAL_AI', 'GREETING', 'FALLBACK', 'ONEDESK')",
            name="ck_chat_messages_response_source",
        ),
        Index("ix_chat_messages_session_id", "session_id"),
        Index("ix_chat_messages_created_at", "created_at"),
    )


class MessageSource(Base):
    __tablename__ = "message_sources"

    id: Mapped[int] = mapped_column(
        BIGINT_ID,
        Identity(always=False),
        primary_key=True,
    )
    assistant_message_id: Mapped[int] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_name: Mapped[str] = mapped_column(String(500), nullable=False)
    section_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    similarity_score: Mapped[float | None] = mapped_column(nullable=True)
    source_order: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    assistant_message: Mapped[ChatMessage] = relationship(back_populates="sources")

    __table_args__ = (
        Index("ix_message_sources_assistant_message_id", "assistant_message_id"),
    )


class MessageFeedback(TimestampMixin, Base):
    __tablename__ = "message_feedback"

    id: Mapped[int] = mapped_column(
        BIGINT_ID,
        Identity(always=False),
        primary_key=True,
    )
    assistant_message_id: Mapped[int] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("chatbot_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback_type: Mapped[str] = mapped_column(String(30), nullable=False)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    assistant_message: Mapped[ChatMessage] = relationship(back_populates="feedback_items")

    __table_args__ = (
        CheckConstraint(
            "rating IS NULL OR rating BETWEEN 1 AND 5",
            name="ck_message_feedback_rating",
        ),
        CheckConstraint(
            "feedback_type IN "
            "('HELPFUL', 'NOT_HELPFUL', 'INCORRECT', 'INCOMPLETE', "
            "'WRONG_POLICY', 'OTHER')",
            name="ck_message_feedback_type",
        ),
        UniqueConstraint(
            "assistant_message_id",
            "user_id",
            name="uq_message_feedback_message_user",
        ),
        Index("ix_message_feedback_assistant_message_id", "assistant_message_id"),
        Index("ix_message_feedback_user_id", "user_id"),
    )


class UnansweredQuestion(TimestampMixin, Base):
    __tablename__ = "unanswered_questions"

    id: Mapped[int] = mapped_column(
        BIGINT_ID,
        Identity(always=False),
        primary_key=True,
    )
    user_message_id: Mapped[int] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    normalized_question: Mapped[str] = mapped_column(String(1000), nullable=False)
    detected_topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occurrence_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="1",
    )
    review_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="PENDING",
    )
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    improvement_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "review_status IN ('PENDING', 'REVIEWED', 'RESOLVED', 'IGNORED')",
            name="ck_unanswered_questions_review_status",
        ),
        UniqueConstraint(
            "normalized_question",
            name="uq_unanswered_questions_normalized_question",
        ),
        Index("ix_unanswered_questions_review_status", "review_status"),
        Index("ix_unanswered_questions_created_at", "created_at"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(
        BIGINT_ID,
        Identity(always=False),
        primary_key=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("chatbot_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result: Mapped[str] = mapped_column(String(50), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    metadata_json: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_action", "action"),
    )
