from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.core.config import get_settings

settings = get_settings()

engine: AsyncEngine | None = None
AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None

if settings.async_database_url:
    engine = create_async_engine(
        settings.async_database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
    )
    AsyncSessionLocal = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )


async def get_db_session() -> AsyncIterator[AsyncSession]:
    if AsyncSessionLocal is None:
        raise RuntimeError(
            "DATABASE_URL is not configured. Set it before using chat history APIs."
        )

    async with AsyncSessionLocal() as session:
        yield session
