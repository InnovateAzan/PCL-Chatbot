from __future__ import annotations

import logging
from collections.abc import Iterator
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _redact_database_url(database_url: str) -> str:
    if not database_url:
        return ""

    parts = urlsplit(database_url)
    if "@" not in parts.netloc:
        return database_url

    credentials, host = parts.netloc.rsplit("@", 1)
    username = credentials.split(":", 1)[0]
    redacted_netloc = f"{username}:***@{host}"
    return urlunsplit(
        (
            parts.scheme,
            redacted_netloc,
            parts.path,
            parts.query,
            parts.fragment,
        )
    )


def _sync_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+asyncpg://"):
        database_url = database_url.replace(
            "postgresql+asyncpg://",
            "postgresql+psycopg2://",
            1,
        )

    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://",
            "postgresql+psycopg2://",
            1,
        )

    return _quote_database_credentials(database_url)


def _quote_database_credentials(database_url: str) -> str:
    parts = urlsplit(database_url)
    if not parts.username or not parts.hostname:
        return database_url

    username = quote(unquote(parts.username), safe="")
    password = (
        f":{quote(unquote(parts.password), safe='')}"
        if parts.password is not None
        else ""
    )
    host = parts.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{parts.port}" if parts.port is not None else ""
    netloc = f"{username}{password}@{host}{port}"
    return urlunsplit(
        (
            parts.scheme,
            netloc,
            parts.path,
            parts.query,
            parts.fragment,
        )
    )


engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None

if settings.database_url:
    try:
        engine = create_engine(
            _sync_database_url(settings.database_url),
            pool_pre_ping=True,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            future=True,
        )
        SessionLocal = sessionmaker(
            bind=engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        )
        logger.info(
            "Configured PostgreSQL connection: %s",
            _redact_database_url(settings.database_url),
        )
    except SQLAlchemyError:
        logger.exception("Could not configure PostgreSQL engine.")


def get_db() -> Iterator[Session]:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured.")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_connection() -> dict[str, object]:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured.")

    with SessionLocal() as db:
        row = db.execute(
            text(
                "select current_database() as database_name, "
                "current_user as user_name, "
                "inet_server_addr() as server_ip, "
                "inet_server_port() as server_port"
            )
        ).mappings().one()
        return dict(row)
