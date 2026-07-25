"""
Database session factory for async SQLAlchemy.
Configured from the DATABASE_URL environment variable.

The engine is created lazily on first access so the module can be imported
safely in test environments without a real database URL.
Tests override get_db via FastAPI dependency_overrides.
"""
import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------

def _resolve_db_url() -> str:
    """
    Return the database URL, normalising the driver prefix for asyncpg.

    Render and Supabase provide URLs in the form:
        postgresql://user:pass@host/db
    SQLAlchemy's async engine requires:
        postgresql+asyncpg://user:pass@host/db

    Falls back to in-memory SQLite only when DATABASE_URL is not set,
    which happens exclusively in local unit-test environments.
    """
    url = os.environ.get("DATABASE_URL", "")

    if not url:
        # Unit-test fallback — never reached in production because Render
        # requires DATABASE_URL to be set before the service starts.
        return "sqlite+aiosqlite:///:memory:"

    # Rewrite sync postgres:// → postgresql+asyncpg://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    return url


DATABASE_URL: str = _resolve_db_url()

# ---------------------------------------------------------------------------
# Engine & session factory — created once at import time.
# SQLAlchemy does NOT open a real connection here; the pool connects lazily.
# ---------------------------------------------------------------------------

engine = create_async_engine(
    DATABASE_URL,
    echo=False,      # set True locally for SQL debug logging
    future=True,
    pool_pre_ping=True,   # drop stale connections automatically
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ---------------------------------------------------------------------------
# ORM base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Shared declarative base for all SQLAlchemy ORM models."""
    __allow_unmapped__ = True


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a request-scoped async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
