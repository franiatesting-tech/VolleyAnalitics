"""Async SQLAlchemy engine/session. PostgreSQL is the sole source of truth
(see ADR-001) -- this module owns nothing about Better Auth's own tables,
only the Alembic-migrated tables in volley_domain.models.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from volley_api.core.config import get_settings


def _async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


_engine = create_async_engine(_async_url(get_settings().database_url), pool_pre_ping=True)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with _session_factory() as session:
        yield session


async def check_db_connection() -> bool:
    from sqlalchemy import text

    try:
        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
