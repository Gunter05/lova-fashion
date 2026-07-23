"""
Async SQLAlchemy engine, session factory, and declarative Base.

All ORM models import `Base` from here.
The async session is provided via `get_db` (FastAPI dependency).

Environment variable expected:
    DATABASE_URL — standard postgresql:// URL (the driver prefix is
    rewritten to postgresql+asyncpg:// automatically so both sync
    tools (psycopg2 scripts) and this module share the same env var).
"""

import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from dotenv import load_dotenv

load_dotenv()

# Convert a plain postgres(ql):// URL to the asyncpg driver variant.
_raw_url: str = os.environ.get("DATABASE_URL", "")
if _raw_url.startswith("postgres://"):
    _raw_url = _raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif _raw_url.startswith("postgresql://"):
    _raw_url = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)

DATABASE_URL: str = _raw_url

engine = create_async_engine(DATABASE_URL, echo=False, future=True)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


async def get_db() -> AsyncSession:
    """FastAPI dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        yield session
