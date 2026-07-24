# Feature: auth-user-profile, Property 8: Measurement Event Idempotence Guard
"""
Property 8: Measurement Event Idempotence Guard

Re-delivering the same `measurements.estimated` event payload any number of
times shall NOT create additional Mensuration records.  The count of Mensuration
rows for a User must always equal the number of *distinct* valid event payloads
processed, not the total number of delivery attempts.

Validates: Requirements 9.5
Pattern: Idempotence — repeated delivery of the same event produces no additional state
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.modules.auth_catalogues.events.handlers import handle_measurements_estimated
from app.db.models import MensurationModel

# ── In-memory SQLite helpers ──────────────────────────────────────────────────

SQLITE_URL = "sqlite+aiosqlite:///:memory:"
TEST_CNI = "EVT000001"


def _make_engine_and_session():
    engine = create_async_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    return engine, session_factory


async def _setup_schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                cni              VARCHAR(9)   NOT NULL PRIMARY KEY,
                nom              VARCHAR(100) NOT NULL,
                email            VARCHAR(255) NOT NULL UNIQUE,
                mot_de_passe     TEXT         NOT NULL,
                role             VARCHAR(20)  NOT NULL,
                is_active        BOOLEAN      NOT NULL DEFAULT 1,
                date_inscription DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS mensuration (
                id_mesure          VARCHAR(36)  NOT NULL PRIMARY KEY,
                cni                VARCHAR(9)   NOT NULL REFERENCES users(cni) ON DELETE CASCADE,
                tour_poitrine      NUMERIC(6,2) NOT NULL,
                tour_taille        NUMERIC(6,2) NOT NULL,
                tour_hanches       NUMERIC(6,2) NOT NULL,
                longueur_bras      NUMERIC(6,2) NOT NULL,
                hauteur            NUMERIC(6,2) NOT NULL,
                date_mensuration   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                source_event_hash  TEXT         UNIQUE
            )
        """))
        await conn.execute(text("""
            INSERT OR IGNORE INTO users (cni, nom, email, mot_de_passe, role)
            VALUES (:cni, 'Event Test User', 'evtuser@example.com', 'hashed', 'CLIENT')
        """), {"cni": TEST_CNI})


# ── Module-scoped shared engine/session_factory ───────────────────────────────

_engine = None
_session_factory = None


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    global _engine, _session_factory
    _engine, _session_factory = _make_engine_and_session()
    _run_sync(_setup_schema(_engine))
    yield
    _run_sync(_engine.dispose())


# ── Helper: count mensuration rows matching a source_event_hash ───────────────

async def _count_rows_for_hash(session_factory, source_event_hash: str) -> int:
    async with session_factory() as session:
        result = await session.execute(
            select(MensurationModel).where(
                MensurationModel.source_event_hash == source_event_hash
            )
        )
        return len(result.scalars().all())


def _run_sync(coro):
    """Run a coroutine synchronously, creating a new event loop if needed."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError('closed')
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


async def _run_idempotence(n_deliveries: int, payload: dict) -> int:
    """Deliver the same payload n times; return the final row count for that hash."""
    import hashlib
    # Use a unique table-scoped session per delivery so each call has commit semantics
    for _ in range(n_deliveries):
        async with _session_factory() as session:
            try:
                await handle_measurements_estimated(payload, session)
                await session.commit()
            except Exception:
                await session.rollback()

    h = hashlib.sha256(
        f"{payload['cni']}{payload['tour_poitrine']}{payload['tour_taille']}"
        f"{payload['tour_hanches']}{payload['longueur_bras']}{payload['hauteur']}"
        f"{payload['source_timestamp']}".encode()
    ).hexdigest()

    return await _count_rows_for_hash(_session_factory, h)


# ── Property 8 ────────────────────────────────────────────────────────────────

@given(n=st.integers(min_value=1, max_value=5))
@settings(max_examples=50, deadline=None)
def test_measurement_event_idempotence(n: int) -> None:
    """
    **Validates: Requirements 9.5**

    Re-delivering the same measurements.estimated payload N times (1 ≤ N ≤ 5)
    must result in exactly 1 mensuration row — not N rows.
    """
    # Use a unique source_timestamp per Hypothesis example so rows don't bleed
    # across runs; the property still exercises re-delivery within the same call.
    source_ts = f"2025-07-15T09:55:{n:02d}Z-{uuid.uuid4().hex[:8]}"
    payload = {
        "cni": TEST_CNI,
        "tour_poitrine": 90.5,
        "tour_taille": 70.0,
        "tour_hanches": 95.0,
        "longueur_bras": 60.0,
        "hauteur": 165.0,
        "source_timestamp": source_ts,
    }

    row_count = _run_sync(
        _run_idempotence(n, payload)
    )

    assert row_count == 1, (
        f"Expected exactly 1 mensuration row after {n} deliveries of the same event, "
        f"but found {row_count}."
    )
