from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ExistingBase(DeclarativeBase):
    """ORM mappings for the already-created OneAssist PostgreSQL tables."""


class User(ExistingBase):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(255))
    department: Mapped[str | None] = mapped_column(String(255))


class ChatSession(ExistingBase):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_uuid: Mapped[str | None] = mapped_column(UUID(as_uuid=False))
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    title: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))


class ChatMessage(ExistingBase):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int | None] = mapped_column(BigInteger)
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    role: Mapped[str | None] = mapped_column(String(50))
    message_text: Mapped[str | None] = mapped_column(Text)
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    is_answered: Mapped[bool | None] = mapped_column(Boolean)


class MessageSource(ExistingBase):
    __tablename__ = "message_sources"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger)
    document_name: Mapped[str | None] = mapped_column(String(500))
    page_number: Mapped[int | None] = mapped_column(Integer)
    chunk_id: Mapped[str | None] = mapped_column(String(255))
    similarity_score: Mapped[float | None] = mapped_column(Float)


class Feedback(ExistingBase):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_id: Mapped[int | None] = mapped_column(BigInteger)
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    rating: Mapped[str | None] = mapped_column(String(50))
    comments: Mapped[str | None] = mapped_column(Text)


class UnansweredQuestion(ExistingBase):
    __tablename__ = "unanswered_questions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_message_id: Mapped[int | None] = mapped_column(BigInteger)
    question_text: Mapped[str | None] = mapped_column(Text)
    normalized_question: Mapped[str | None] = mapped_column(Text)


class Document(ExistingBase):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_name: Mapped[str | None] = mapped_column(String(500))
    file_path: Mapped[str | None] = mapped_column(Text)


class DocumentChunk(ExistingBase):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int | None] = mapped_column(BigInteger)
    chunk_text: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)


class AuditLog(ExistingBase):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str | None] = mapped_column(String(100))
    result: Mapped[str | None] = mapped_column(String(50))
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)
