from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import MetaData, Table, and_, inspect, or_, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.core.existing_database import engine
from backend.app.models.schemas import ChatResponse, SourceReference

logger = logging.getLogger(__name__)

GUEST_EMAIL = "guest@oneassist.local"


@dataclass
class PersistedChat:
    session_uuid: str | None = None
    session_id: int | None = None
    user_message_id: int | None = None
    assistant_message_id: int | None = None


class ExistingPostgresRepository:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.engine: Engine = db.get_bind()
        self.metadata = MetaData()
        self._tables: dict[str, Table | None] = {}

    def get_or_create_user(
        self,
        *,
        user_email: str | None,
        display_name: str | None,
        department: str | None,
    ) -> dict[str, Any]:
        table = self._table("users")
        email = self._normalize_email(user_email)
        existing = self._find_one(
            table,
            {"email": email, "user_email": email},
            mode="or",
        )

        if existing:
            self._safe_update_by_pk(
                table,
                existing,
                {
                    "display_name": display_name,
                    "name": display_name,
                    "department": department,
                    "last_seen_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                },
            )
            return existing

        return self._insert(
            table,
            {
                "email": email,
                "user_email": email,
                "display_name": display_name or "Guest User",
                "name": display_name or "Guest User",
                "department": department,
                "is_active": True,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "last_seen_at": datetime.now(UTC),
            },
        )

    def get_or_create_session(
        self,
        *,
        user_id: int | None,
        session_uuid: str | None,
    ) -> dict[str, Any]:
        table = self._table("chat_sessions")

        if session_uuid:
            existing = self._find_one(
                table,
                {"session_uuid": session_uuid, "uuid": session_uuid, "id": session_uuid},
                mode="or",
            )
            if existing and self._same_user(existing, user_id):
                return existing

        new_uuid = session_uuid or str(uuid.uuid4())
        return self._insert(
            table,
            {
                "session_uuid": new_uuid,
                "uuid": new_uuid,
                "user_id": user_id,
                "title": "New chat",
                "status": "active",
                "created_at": datetime.now(UTC),
                "started_at": datetime.now(UTC),
                "last_activity_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
        )

    def save_message(
        self,
        *,
        session: dict[str, Any],
        user_id: int | None,
        role: str,
        message_text: str,
        response_time_ms: int | None = None,
        is_answered: bool | None = None,
        response_source: str | None = None,
    ) -> dict[str, Any]:
        table = self._table("chat_messages")
        session_id = self._row_id(session)
        session_uuid = self._row_uuid(session)
        return self._insert(
            table,
            {
                "session_id": session_id,
                "chat_session_id": session_id,
                "session_uuid": session_uuid,
                "user_id": user_id,
                "role": role,
                "message_text": message_text,
                "content": message_text,
                "message": message_text,
                "response_text": message_text if role == "assistant" else None,
                "response_time_ms": response_time_ms,
                "is_answered": is_answered,
                "response_source": response_source,
                "created_at": datetime.now(UTC),
            },
        )

    def save_sources(
        self,
        *,
        assistant_message_id: int | None,
        sources: list[SourceReference],
    ) -> None:
        if not assistant_message_id:
            return

        table = self._table("message_sources")
        for index, source in enumerate(sources, start=1):
            self._insert(
                table,
                {
                    "message_id": assistant_message_id,
                    "assistant_message_id": assistant_message_id,
                    "document_name": source.document_name,
                    "section_name": source.section,
                    "section": source.section,
                    "page_number": source.page_number,
                    "chunk_id": source.chunk_id,
                    "similarity_score": source.similarity_score,
                    "source_order": index,
                    "snippet": source.snippet,
                    "created_at": datetime.now(UTC),
                },
            )

    def save_unanswered(
        self,
        *,
        user_message_id: int | None,
        question: str,
    ) -> None:
        if not user_message_id:
            return

        table = self._table("unanswered_questions")
        normalized = self._normalize_question(question)
        existing = self._find_one(
            table,
            {"normalized_question": normalized},
            mode="or",
        )

        if existing:
            count = existing.get("occurrence_count")
            try:
                next_count = int(count or 1) + 1
            except (TypeError, ValueError):
                next_count = 2
            self._safe_update_by_pk(
                table,
                existing,
                {
                    "occurrence_count": next_count,
                    "updated_at": datetime.now(UTC),
                },
            )
            return

        self._insert(
            table,
            {
                "user_message_id": user_message_id,
                "question_text": question,
                "question": question,
                "normalized_question": normalized,
                "review_status": "pending",
                "occurrence_count": 1,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
        )

    def update_session_activity(self, session: dict[str, Any]) -> None:
        table = self._table("chat_sessions")
        self._safe_update_by_pk(
            table,
            session,
            {
                "last_activity_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
        )

    def save_feedback(
        self,
        *,
        message_id: int,
        rating: str,
        comments: str | None,
        user_email: str | None,
    ) -> dict[str, Any]:
        message = self.get_message(message_id)
        if not message:
            raise ValueError("Message does not exist.")

        user = self.get_or_create_user(
            user_email=user_email,
            display_name=None,
            department=None,
        )
        table = self._table("feedback")
        return self._insert(
            table,
            {
                "message_id": message_id,
                "assistant_message_id": message_id,
                "user_id": self._row_id(user),
                "rating": rating,
                "comments": comments,
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
        )

    def get_message(self, message_id: int) -> dict[str, Any] | None:
        table = self._table("chat_messages")
        pk = self._pk_column(table)
        if not pk:
            return None

        row = self.db.execute(
            select(table).where(table.c[pk] == message_id).limit(1)
        ).mappings().first()
        return dict(row) if row else None

    def list_sessions_for_user(self, *, user_email: str) -> list[dict[str, Any]]:
        user = self.get_or_create_user(
            user_email=user_email,
            display_name=None,
            department=None,
        )
        table = self._table("chat_sessions")
        user_id = self._row_id(user)
        if user_id is None or "user_id" not in table.c:
            return []

        order_column = (
            table.c.last_activity_at
            if "last_activity_at" in table.c
            else table.c.created_at
            if "created_at" in table.c
            else table.c.user_id
        )
        rows = self.db.execute(
            select(table)
            .where(table.c.user_id == user_id)
            .order_by(order_column.desc())
        ).mappings().all()
        return [dict(row) for row in rows]

    def get_session_with_messages(
        self,
        *,
        session_uuid: str,
        user_email: str,
    ) -> dict[str, Any] | None:
        user = self.get_or_create_user(
            user_email=user_email,
            display_name=None,
            department=None,
        )
        session_table = self._table("chat_sessions")
        session = self._find_one(
            session_table,
            {"session_uuid": session_uuid, "uuid": session_uuid, "id": session_uuid},
            mode="or",
        )
        if not session or not self._same_user(session, self._row_id(user)):
            return None

        if str(session.get("status") or "").upper() == "ENDED":
            return None

        message_table = self._table("chat_messages")
        session_id = self._row_id(session)
        clauses = []
        if session_id is not None:
            for column in ("session_id", "chat_session_id"):
                if column in message_table.c:
                    clauses.append(message_table.c[column] == session_id)
        for column in ("session_uuid", "chat_session_uuid"):
            if column in message_table.c:
                clauses.append(message_table.c[column] == session_uuid)

        if not clauses:
            messages = []
        else:
            order_column = (
                message_table.c.created_at
                if "created_at" in message_table.c
                else message_table.c.id
            )
            rows = self.db.execute(
                select(message_table)
                .where(clauses[0] if len(clauses) == 1 else or_(*clauses))
                .order_by(order_column.asc())
            ).mappings().all()
            messages = [dict(row) for row in rows]

        self._attach_sources_to_messages(messages)

        return {"session": session, "messages": messages}

    def end_session(
        self,
        *,
        session_uuid: str,
        user_email: str,
    ) -> bool:
        user = self.get_or_create_user(
            user_email=user_email,
            display_name=None,
            department=None,
        )
        session_table = self._table("chat_sessions")
        session = self._find_one(
            session_table,
            {"session_uuid": session_uuid, "uuid": session_uuid, "id": session_uuid},
            mode="or",
        )
        if not session or not self._same_user(session, self._row_id(user)):
            return False

        self._safe_update_by_pk(
            session_table,
            session,
            {
                "status": "ENDED",
                "ended_at": datetime.now(UTC),
                "last_activity_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
        )
        self.db.commit()
        return True

    def _table(self, table_name: str) -> Table:
        if table_name not in self._tables:
            connection = self.db.connection()
            if not inspect(connection).has_table(table_name):
                raise RuntimeError(f"Required table does not exist: {table_name}")
            self._tables[table_name] = Table(
                table_name,
                self.metadata,
                autoload_with=connection,
            )

        table = self._tables[table_name]
        if table is None:
            raise RuntimeError(f"Table could not be loaded: {table_name}")
        return table

    def _insert(self, table: Table, values: dict[str, Any]) -> dict[str, Any]:
        clean_values = {
            key: value
            for key, value in values.items()
            if key in table.c and value is not None
        }
        logger.info(
            "PostgreSQL insert starting: table=%s columns=%s",
            table.name,
            sorted(clean_values.keys()),
        )
        statement = table.insert().values(**clean_values)
        pk = self._pk_column(table)
        try:
            if pk:
                statement = statement.returning(table)
                row = self.db.execute(statement).mappings().one()
                saved = dict(row)
                logger.info(
                    "PostgreSQL insert successful: table=%s %s=%s",
                    table.name,
                    pk,
                    saved.get(pk),
                )
                return saved

            result = self.db.execute(statement)
            saved = dict(clean_values) | {
                "id": result.inserted_primary_key[0]
                if result.inserted_primary_key
                else None
            }
            logger.info("PostgreSQL insert successful: table=%s", table.name)
            return saved
        except SQLAlchemyError:
            logger.exception(
                "PostgreSQL insert failed: table=%s columns=%s",
                table.name,
                sorted(clean_values.keys()),
            )
            raise

    def _find_one(
        self,
        table: Table,
        candidates: dict[str, Any],
        *,
        mode: str = "or",
    ) -> dict[str, Any] | None:
        clauses = [
            table.c[column] == value
            for column, value in candidates.items()
            if column in table.c and value is not None
        ]

        if not clauses:
            return None

        condition = clauses[0]
        for clause in clauses[1:]:
            condition = (condition | clause) if mode == "or" else and_(condition, clause)

        row = self.db.execute(select(table).where(condition).limit(1)).mappings().first()
        return dict(row) if row else None

    def _safe_update_by_pk(
        self,
        table: Table,
        row: dict[str, Any],
        values: dict[str, Any],
    ) -> None:
        pk = self._pk_column(table)
        if not pk or pk not in row:
            return
        clean_values = {
            key: value
            for key, value in values.items()
            if key in table.c and value is not None
        }
        if not clean_values:
            return
        self.db.execute(
            update(table)
            .where(table.c[pk] == row[pk])
            .values(**clean_values)
        )

    def _attach_sources_to_messages(self, messages: list[dict[str, Any]]) -> None:
        assistant_message_ids = [
            self._row_id(message)
            for message in messages
            if str(message.get("role") or "").lower() in {"assistant", "bot"}
            and self._row_id(message) is not None
        ]
        if not assistant_message_ids:
            return

        try:
            source_table = self._table("message_sources")
        except RuntimeError:
            return

        clauses = []
        for column in ("message_id", "assistant_message_id"):
            if column in source_table.c:
                clauses.append(source_table.c[column].in_(assistant_message_ids))

        if not clauses:
            return

        order_column = (
            source_table.c.source_order
            if "source_order" in source_table.c
            else source_table.c.id
            if "id" in source_table.c
            else None
        )
        statement = select(source_table).where(
            clauses[0] if len(clauses) == 1 else or_(*clauses)
        )
        if order_column is not None:
            statement = statement.order_by(order_column.asc())

        rows = self.db.execute(statement).mappings().all()
        sources_by_message_id: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            source = dict(row)
            message_id = source.get("message_id") or source.get("assistant_message_id")
            try:
                normalized_message_id = int(message_id)
            except (TypeError, ValueError):
                continue
            sources_by_message_id.setdefault(normalized_message_id, []).append(source)

        for message in messages:
            message_id = self._row_id(message)
            if message_id is not None:
                message["sources"] = sources_by_message_id.get(message_id, [])

    @staticmethod
    def _pk_column(table: Table) -> str | None:
        primary_keys = list(table.primary_key.columns)
        if primary_keys:
            return primary_keys[0].name
        if "id" in table.c:
            return "id"
        return None

    @staticmethod
    def _row_id(row: dict[str, Any]) -> int | None:
        value = row.get("id")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _row_uuid(row: dict[str, Any]) -> str | None:
        value = row.get("session_uuid") or row.get("uuid")
        return str(value) if value is not None else None

    @staticmethod
    def _same_user(row: dict[str, Any], user_id: int | None) -> bool:
        if user_id is None:
            return True
        row_user_id = row.get("user_id")
        return row_user_id is None or str(row_user_id) == str(user_id)

    @staticmethod
    def _normalize_email(user_email: str | None) -> str:
        email = (user_email or "").strip().lower()
        return email or GUEST_EMAIL

    @staticmethod
    def _normalize_question(question: str) -> str:
        normalized = question.lower().strip()
        normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized[:1000]


def persist_chat_best_effort(
    *,
    db: Session,
    message: str,
    response: ChatResponse,
    response_time_ms: int,
    user_email: str | None,
    display_name: str | None,
    department: str | None,
    session_uuid: str | None,
) -> PersistedChat:
    repository = ExistingPostgresRepository(db)
    logger.info("Starting existing PostgreSQL chat save flow.")
    user = repository.get_or_create_user(
        user_email=user_email,
        display_name=display_name,
        department=department,
    )
    logger.info("User created: id=%s email=%s", repository._row_id(user), user.get("email") or user.get("user_email"))
    print("User created")
    chat_session = repository.get_or_create_session(
        user_id=repository._row_id(user),
        session_uuid=session_uuid,
    )
    logger.info(
        "Session created: id=%s session_uuid=%s",
        repository._row_id(chat_session),
        repository._row_uuid(chat_session),
    )
    print("Session created")
    user_message = repository.save_message(
        session=chat_session,
        user_id=repository._row_id(user),
        role="user",
        message_text=message,
        is_answered=not response.fallback,
    )
    logger.info("User message saved: id=%s", repository._row_id(user_message))
    print("User message saved")
    assistant_message = repository.save_message(
        session=chat_session,
        user_id=repository._row_id(user),
        role="assistant",
        message_text=response.answer,
        response_time_ms=response_time_ms,
        is_answered=not response.fallback,
        response_source=response.response_source or response.provider,
    )
    logger.info("Assistant message saved: id=%s", repository._row_id(assistant_message))
    print("Assistant message saved")
    repository.save_sources(
        assistant_message_id=repository._row_id(assistant_message),
        sources=response.sources,
    )
    if _is_unanswered(response):
        repository.save_unanswered(
            user_message_id=repository._row_id(user_message),
            question=message,
        )
    repository.update_session_activity(chat_session)
    logger.info("PostgreSQL commit starting.")
    try:
        db.commit()
    except SQLAlchemyError:
        logger.exception("PostgreSQL commit failed.")
        raise
    logger.info("PostgreSQL commit successful.")
    print("Commit successful")
    return PersistedChat(
        session_uuid=repository._row_uuid(chat_session),
        session_id=repository._row_id(chat_session),
        user_message_id=repository._row_id(user_message),
        assistant_message_id=repository._row_id(assistant_message),
    )


def _is_unanswered(response: ChatResponse) -> bool:
    if response.fallback:
        return True
    answer = response.answer.lower()
    return "information not available" in answer or "not covered" in answer


def rollback_safely(db: Session) -> None:
    try:
        db.rollback()
    except SQLAlchemyError:
        logger.exception("Could not rollback PostgreSQL session.")
