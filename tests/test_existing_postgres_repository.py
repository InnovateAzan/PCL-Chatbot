from __future__ import annotations

from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.models.schemas import ChatResponse, SourceReference
from backend.app.repositories.existing_postgres import (
    ExistingPostgresRepository,
    persist_chat_best_effort,
)


def make_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                create table users (
                    id integer primary key autoincrement,
                    email text unique,
                    display_name text,
                    department text,
                    created_at text,
                    updated_at text,
                    last_seen_at text
                )
                """
            )
        )
        connection.execute(
            text(
                """
                create table chat_sessions (
                    id integer primary key autoincrement,
                    session_uuid text unique,
                    user_id integer,
                    title text,
                    status text,
                    created_at text,
                    started_at text,
                    last_activity_at text,
                    updated_at text
                )
                """
            )
        )
        connection.execute(
            text(
                """
                create table chat_messages (
                    id integer primary key autoincrement,
                    session_id integer,
                    session_uuid text,
                    user_id integer,
                    role text,
                    message_text text,
                    response_time_ms integer,
                    is_answered boolean,
                    response_source text,
                    created_at text
                )
                """
            )
        )
        connection.execute(
            text(
                """
                create table message_sources (
                    id integer primary key autoincrement,
                    message_id integer,
                    document_name text,
                    page_number integer,
                    chunk_id text,
                    similarity_score real,
                    source_order integer,
                    created_at text
                )
                """
            )
        )
        connection.execute(
            text(
                """
                create table unanswered_questions (
                    id integer primary key autoincrement,
                    user_message_id integer,
                    question_text text,
                    normalized_question text,
                    occurrence_count integer,
                    review_status text,
                    created_at text,
                    updated_at text
                )
                """
            )
        )
        connection.execute(
            text(
                """
                create table feedback (
                    id integer primary key autoincrement,
                    message_id integer,
                    user_id integer,
                    rating text,
                    comments text,
                    created_at text,
                    updated_at text
                )
                """
            )
        )

    return sessionmaker(bind=engine, future=True)()


def test_persist_chat_best_effort_saves_user_session_messages_sources():
    db = make_session()
    response = ChatResponse(
        answer="Use the laptop eligibility policy.",
        fallback=False,
        provider="gemini-policy",
        sources=[
            SourceReference(
                document_name="0038 - PCL - IT Asset Endpoint Management Policy.docx",
                page_number=2,
                chunk_id="abc",
                similarity_score=0.9,
            )
        ],
    )

    result = persist_chat_best_effort(
        db=db,
        message="laptop policy",
        response=response,
        response_time_ms=123,
        user_email="azan@example.com",
        display_name="Muhammad Azan",
        department="IT",
        session_uuid=None,
    )

    assert result.session_uuid
    assert result.user_message_id is not None
    assert result.assistant_message_id is not None
    assert db.execute(text("select count(*) from users")).scalar_one() == 1
    assert db.execute(text("select count(*) from chat_sessions")).scalar_one() == 1
    assert db.execute(text("select count(*) from chat_messages")).scalar_one() == 2
    assert db.execute(text("select count(*) from message_sources")).scalar_one() == 1


def test_guest_user_is_reused_and_feedback_validates_message():
    db = make_session()
    repository = ExistingPostgresRepository(db)
    user_one = repository.get_or_create_user(
        user_email=None,
        display_name=None,
        department=None,
    )
    user_two = repository.get_or_create_user(
        user_email=None,
        display_name=None,
        department=None,
    )
    session = repository.get_or_create_session(
        user_id=user_one["id"],
        session_uuid=None,
    )
    message = repository.save_message(
        session=session,
        user_id=user_one["id"],
        role="assistant",
        message_text="Answer",
    )
    feedback = repository.save_feedback(
        message_id=message["id"],
        rating="helpful",
        comments="Good",
        user_email=None,
    )
    db.commit()

    assert user_one["id"] == user_two["id"]
    assert feedback["rating"] == "helpful"


def test_session_uuid_lookup_does_not_query_integer_id():
    session_uuid = str(uuid4())

    assert ExistingPostgresRepository._session_lookup_candidates(session_uuid) == {
        "session_uuid": session_uuid
    }


def test_integer_session_lookup_queries_only_id():
    assert ExistingPostgresRepository._session_lookup_candidates("42") == {"id": 42}
