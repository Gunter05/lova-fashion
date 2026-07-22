"""
Test configuration for the Fabric Catalog property-based tests.

Sets up an in-memory SQLite database and a FastAPI TestClient that wires the
router under /api/v1, overriding the `get_db` dependency so that every test
runs against a fresh, isolated database with no external connections required.

SQLite is used instead of PostgreSQL so tests run without a Supabase instance.
The UUID primary key columns are stored as strings in SQLite (aiosqlite driver).
"""

import asyncio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.modules.auth_catalogues.router import router


# ---------------------------------------------------------------------------
# In-memory async SQLite engine — shared across the test session
# ---------------------------------------------------------------------------

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the whole test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def engine():
    """Create the async SQLite engine and initialise the schema once per session."""
    eng = create_async_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # single connection shared by all async operations
        echo=False,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture(scope="session")
def session_factory(engine):
    """Return a session factory bound to the in-memory engine."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


# ---------------------------------------------------------------------------
# Per-test database session + TestClient
# ---------------------------------------------------------------------------


@pytest.fixture()
async def db_session(session_factory, engine):
    """
    Yield a fresh AsyncSession for each test and roll back all changes
    afterwards so each test starts from a clean state.
    """
    async with session_factory() as session:
        yield session
        await session.rollback()
        # Truncate all tables to guarantee isolation between tests
        from sqlalchemy import text
        async with engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                await conn.execute(text(f"DELETE FROM {table.name}"))


@pytest.fixture()
def client(db_session):
    """
    Return a synchronous FastAPI TestClient wired to a per-test database
    session.  The `get_db` dependency is overridden so no real DB connection
    is needed.
    """
    from app.database import get_db

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=True) as tc:
        yield tc
