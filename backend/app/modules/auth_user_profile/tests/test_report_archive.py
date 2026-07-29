# Feature: auth-user-profile, Property 11: Report Archive Idempotence
"""
Property 11: Report Archive Idempotence

Re-delivering the same `report.saved` event (same cni + report_id) any number of
times shall NOT create more than one `rapport_archive` row for that (cni, report_id) pair.

Validates: Requirements 12.4
Pattern: Idempotence — repeated delivery of the same event produces no additional state
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.modules.auth_user_profile.events.handlers import handle_report_saved
from app.db.models import RapportArchiveModel


def _run_sync(coro):
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError('closed')
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)



# ── In-memory SQLite helpers ──────────────────────────────────────────────────

SQLITE_URL = "sqlite+aiosqlite:///:memory:"
TEST_CNI = "RPT000001"


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
            CREATE TABLE IF NOT EXISTS rapport_archive (
                id              VARCHAR(36) NOT NULL PRIMARY KEY,
                cni             VARCHAR(9)  NOT NULL REFERENCES users(cni) ON DELETE CASCADE,
                report_id       TEXT        NOT NULL,
                date_generation DATETIME    NOT NULL,
                archived_at     DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (cni, report_id)
            )
        """))
        await conn.execute(text("""
            INSERT OR IGNORE INTO users (cni, nom, email, mot_de_passe, role)
            VALUES (:cni, 'Report Test User', 'rptuser@example.com', 'hashed', 'Client')
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


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _count_rapport_rows(session_factory, cni: str, report_id: str) -> int:
    async with session_factory() as session:
        result = await session.execute(
            select(RapportArchiveModel).where(
                RapportArchiveModel.cni == cni,
                RapportArchiveModel.report_id == report_id,
            )
        )
        return len(result.scalars().all())


async def _run_archive_idempotence(n_deliveries: int, payload: dict) -> int:
    """Deliver the same report.saved payload n times; return final archive row count."""
    for _ in range(n_deliveries):
        async with _session_factory() as session:
            try:
                await handle_report_saved(payload, session)
                await session.commit()
            except Exception:
                await session.rollback()

    return await _count_rapport_rows(
        _session_factory,
        payload["cni"],
        payload["report_id"],
    )


# ── Property 11 ───────────────────────────────────────────────────────────────

@given(n=st.integers(min_value=1, max_value=5))
@settings(max_examples=50, deadline=None)
def test_report_archive_idempotence(n: int) -> None:
    """
    **Validates: Requirements 12.4**

    Re-delivering the same report.saved payload N times (1 ≤ N ≤ 5)
    must result in exactly 1 rapport_archive row for (cni, report_id) — not N rows.
    """
    # Use a per-example unique report_id so different Hypothesis examples
    # don't share rows; the idempotence property is tested by the n-delivery loop.
    report_id = f"RPT-2025-{n:03d}-{uuid.uuid4().hex[:8]}"
    payload = {
        "cni": TEST_CNI,
        "report_id": report_id,
        "date_generation": datetime.now(timezone.utc).isoformat(),
    }

    row_count = _run_sync(
        _run_archive_idempotence(n, payload)
    )

    assert row_count == 1, (
        f"Expected exactly 1 rapport_archive row after {n} deliveries of the same "
        f"(cni={TEST_CNI!r}, report_id={report_id!r}), but found {row_count}."
    )
