"""
Database session factory for async SQLAlchemy.
Configured from the DATABASE_URL environment variable.

In test environments where DATABASE_URL is not set, a no-op SQLite URL is used
so the module can be imported without crashing.  Tests override get_db via
FastAPI dependency_overrides and never actually use this engine.
"""
import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# Fall back to an in-memory SQLite URL so the module can be safely imported
# in test environments where DATABASE_URL is not configured.
# The real PostgreSQL URL must be provided in production via the DATABASE_URL
# environment variable.
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite+aiosqlite:///:memory:",  # safe import-time fallback for tests
)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # set True for SQL debug logging
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    __allow_unmapped__ = True

async def get_db() -> AsyncSession:
    """FastAPI dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
