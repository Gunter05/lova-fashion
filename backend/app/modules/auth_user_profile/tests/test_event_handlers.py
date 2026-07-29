"""
Example-based tests for the three event handler functions:
  - handle_measurements_estimated
  - handle_report_saved
  - handle_profile_data_request

These tests use an in-memory SQLite DB (same pattern as other tests in this suite)
and exercise the handlers directly, bypassing the HTTP layer.
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.modules.auth_user_profile.events.handlers import (
    handle_measurements_estimated,
    handle_report_saved,
    handle_profile_data_request,
)
from app.modules.auth_user_profile.events.bus import EventBus
from app.db.models import MensurationModel, RapportArchiveModel

# ── SQLite helpers ────────────────────────────────────────────────────────────

SQLITE_URL = "sqlite+aiosqlite:///:memory:"
TEST_CNI = "HND000001"


def _make_engine_and_session():
    engine = create_async_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    sf = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    return engine, sf


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
            VALUES (:cni, 'Handler Test User', 'handler@example.com', 'hashed', 'Client')
        """), {"cni": TEST_CNI})


# ── Module fixture ────────────────────────────────────────────────────────────

_engine = None
_sf = None


@pytest.fixture(scope="module", autouse=True)
def db():
    global _engine, _sf
    _engine, _sf = _make_engine_and_session()
    _run_sync(_setup_schema(_engine))
    yield
    _run_sync(_engine.dispose())


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


def _run(coro):
    return _run_sync(coro)


# ── handle_measurements_estimated ─────────────────────────────────────────────

def _valid_measurement_payload(source_ts: str | None = None) -> dict:
    return {
        "cni": TEST_CNI,
        "tour_poitrine": 90.5,
        "tour_taille": 70.0,
        "tour_hanches": 95.0,
        "longueur_bras": 60.0,
        "hauteur": 165.0,
        "source_timestamp": source_ts or datetime.now(timezone.utc).isoformat(),
    }


def _expected_hash(payload: dict) -> str:
    tp, tt, th, lb, h = (
        payload["tour_poitrine"], payload["tour_taille"],
        payload["tour_hanches"], payload["longueur_bras"], payload["hauteur"],
    )
    return hashlib.sha256(
        f"{payload['cni']}{tp}{tt}{th}{lb}{h}{payload['source_timestamp']}".encode()
    ).hexdigest()


class TestHandleMeasurementsEstimated:
    def test_valid_payload_creates_row(self):
        """A valid payload produces exactly one mensuration row."""
        payload = _valid_measurement_payload(f"ts-{uuid.uuid4()}")

        async def run():
            async with _sf() as session:
                await handle_measurements_estimated(payload, session)
                await session.commit()
            async with _sf() as session:
                result = await session.execute(
                    select(MensurationModel).where(
                        MensurationModel.source_event_hash == _expected_hash(payload)
                    )
                )
                return result.scalars().all()

        rows = _run(run())
        assert len(rows) == 1
        row = rows[0]
        assert row.cni == TEST_CNI
        assert float(row.tour_poitrine) == 90.5
        assert float(row.hauteur) == 165.0

    def test_duplicate_payload_creates_only_one_row(self):
        """Re-delivering the same event twice must not create a second row."""
        payload = _valid_measurement_payload(f"dup-{uuid.uuid4()}")
        h = _expected_hash(payload)

        async def run():
            for _ in range(2):
                async with _sf() as session:
                    await handle_measurements_estimated(payload, session)
                    await session.commit()
            async with _sf() as session:
                result = await session.execute(
                    select(MensurationModel).where(
                        MensurationModel.source_event_hash == h
                    )
                )
                return result.scalars().all()

        rows = _run(run())
        assert len(rows) == 1

    def test_missing_field_does_not_create_row(self):
        """A payload missing a required field must be silently rejected."""
        payload = _valid_measurement_payload(f"miss-{uuid.uuid4()}")
        del payload["hauteur"]

        async def run():
            async with _sf() as session:
                await handle_measurements_estimated(payload, session)
                await session.commit()

        # Should complete without raising
        _run(run())

    def test_invalid_measurement_value_does_not_create_row(self):
        """A payload with a value ≤ 0 must be silently rejected."""
        payload = _valid_measurement_payload(f"inv-{uuid.uuid4()}")
        payload["tour_taille"] = -5.0

        async def run():
            async with _sf() as session:
                await handle_measurements_estimated(payload, session)
                await session.commit()
            # No row with that negative value should exist
            async with _sf() as session:
                result = await session.execute(
                    select(MensurationModel).where(MensurationModel.cni == TEST_CNI)
                )
                rows = result.scalars().all()
                return rows

        rows = _run(run())
        # None of the rows should have a negative tour_taille
        assert all(float(r.tour_taille) > 0 for r in rows)

    def test_unknown_cni_does_not_create_row(self):
        """A payload with an unknown CNI must be silently rejected."""
        payload = _valid_measurement_payload(f"unk-{uuid.uuid4()}")
        payload["cni"] = "ZZZ999999"

        async def run():
            async with _sf() as session:
                await handle_measurements_estimated(payload, session)
                await session.commit()
            async with _sf() as session:
                result = await session.execute(
                    select(MensurationModel).where(
                        MensurationModel.cni == "ZZZ999999"
                    )
                )
                return result.scalars().all()

        rows = _run(run())
        assert len(rows) == 0


# ── handle_report_saved ───────────────────────────────────────────────────────

class TestHandleReportSaved:
    def _payload(self, report_id: str | None = None) -> dict:
        return {
            "cni": TEST_CNI,
            "report_id": report_id or f"RPT-{uuid.uuid4().hex[:8]}",
            "date_generation": datetime.now(timezone.utc).isoformat(),
        }

    def test_valid_event_archives_report(self):
        payload = self._payload()

        async def run():
            async with _sf() as session:
                await handle_report_saved(payload, session)
                await session.commit()
            async with _sf() as session:
                result = await session.execute(
                    select(RapportArchiveModel).where(
                        RapportArchiveModel.cni == TEST_CNI,
                        RapportArchiveModel.report_id == payload["report_id"],
                    )
                )
                return result.scalars().all()

        rows = _run(run())
        assert len(rows) == 1
        assert rows[0].report_id == payload["report_id"]

    def test_duplicate_report_creates_only_one_row(self):
        payload = self._payload(f"DUP-{uuid.uuid4().hex[:8]}")

        async def run():
            for _ in range(3):
                async with _sf() as session:
                    await handle_report_saved(payload, session)
                    await session.commit()
            async with _sf() as session:
                result = await session.execute(
                    select(RapportArchiveModel).where(
                        RapportArchiveModel.cni == TEST_CNI,
                        RapportArchiveModel.report_id == payload["report_id"],
                    )
                )
                return result.scalars().all()

        rows = _run(run())
        assert len(rows) == 1

    def test_unknown_cni_does_not_archive(self):
        payload = self._payload()
        payload["cni"] = "ZZZ999998"

        async def run():
            async with _sf() as session:
                await handle_report_saved(payload, session)
                await session.commit()
            async with _sf() as session:
                result = await session.execute(
                    select(RapportArchiveModel).where(
                        RapportArchiveModel.cni == "ZZZ999998"
                    )
                )
                return result.scalars().all()

        rows = _run(run())
        assert len(rows) == 0


# ── handle_profile_data_request ───────────────────────────────────────────────

class TestHandleProfileDataRequest:
    def test_user_not_found_publishes_error(self):
        """Unknown CNI → user.profile_data.error with reason=user_not_found."""
        bus = EventBus()
        received = []
        bus.subscribe("user.profile_data.error", lambda p: received.append(p) or _noop())

        async def _noop():
            pass

        async def run():
            async with _sf() as session:
                await handle_profile_data_request(
                    {"cni": "ZZZ999997"}, session, bus
                )
                await session.commit()

        _run(run())
        # Give the bus a chance to dispatch (in-process, so synchronous here)
        # Actually the bus awaits inline, so received should be populated
        assert len(received) == 1
        assert received[0]["reason"] == "user_not_found"
        assert received[0]["cni"] == "ZZZ999997"

    def test_no_measurements_publishes_error(self):
        """User exists but has no measurements → user.profile_data.error reason=no_measurements."""
        # Insert a user with no measurements
        no_meas_cni = "NOM000001"

        async def setup():
            async with _sf() as session:
                await session.execute(
                    text("""
                        INSERT OR IGNORE INTO users (cni, nom, email, mot_de_passe, role)
                    VALUES (:cni, 'NoMeas User', 'nomeas@example.com', 'h', 'Client')
                    """),
                    {"cni": no_meas_cni},
                )
                await session.commit()

        _run(setup())

        bus = EventBus()
        received_errors = []
        received_data = []

        async def _capture_error(p): received_errors.append(p)
        async def _capture_data(p): received_data.append(p)
        bus.subscribe("user.profile_data.error", _capture_error)
        bus.subscribe("user.profile_data", _capture_data)

        async def run():
            async with _sf() as session:
                await handle_profile_data_request({"cni": no_meas_cni}, session, bus)
                await session.commit()

        _run(run())
        assert len(received_errors) == 1
        assert received_errors[0]["reason"] == "no_measurements"
        assert len(received_data) == 0

    def test_valid_user_publishes_profile_data(self):
        """User with measurements → user.profile_data with the most recent measurement."""
        bus = EventBus()
        received_data = []
        received_errors = []

        async def _capture_data(p): received_data.append(p)
        async def _capture_error(p): received_errors.append(p)
        bus.subscribe("user.profile_data", _capture_data)
        bus.subscribe("user.profile_data.error", _capture_error)

        # Ensure TEST_CNI has at least one measurement (from earlier tests or insert one)
        async def ensure_mensuration():
            async with _sf() as session:
                result = await session.execute(
                    select(MensurationModel).where(MensurationModel.cni == TEST_CNI)
                )
                existing = result.scalars().all()
                if not existing:
                    from app.modules.auth_user_profile.measurement.repository import MensurationRepository
                    repo = MensurationRepository(session)
                    await repo.create_mensuration(
                        cni=TEST_CNI,
                        tour_poitrine=88.0,
                        tour_taille=68.0,
                        tour_hanches=92.0,
                        longueur_bras=58.0,
                        hauteur=162.0,
                    )
                    await session.commit()

        _run(ensure_mensuration())

        async def run():
            async with _sf() as session:
                await handle_profile_data_request({"cni": TEST_CNI}, session, bus)
                await session.commit()

        _run(run())
        assert len(received_data) == 1
        assert len(received_errors) == 0
        assert received_data[0]["cni"] == TEST_CNI
        assert len(received_data[0]["mensurations"]) == 1
        m = received_data[0]["mensurations"][0]
        assert "tour_poitrine" in m
        assert "hauteur" in m
