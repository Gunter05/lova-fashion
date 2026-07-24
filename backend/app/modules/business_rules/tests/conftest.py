"""
Test configuration for Module 5 — Ease Allowance Calculation Engine.

Uses an in-memory SQLite database.  The PostgreSQL-specific pg_insert upsert
and the raw-SQL fabric loader are replaced with SQLite-compatible equivalents.
JWT authentication is bypassed by overriding get_current_user.

cv2 / mediapipe are stubbed out via sys.modules so they don't need to be
installed in the test environment (they're only needed for the CV pipeline).
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

# ── Stub absent heavy CV dependencies before any production imports ─────────
# Only stub cv2 and mediapipe (not numpy — Hypothesis uses numpy.ndarray check)
_absent_cv_mods = ("cv2", "mediapipe", "mediapipe.solutions", "mediapipe.solutions.pose")
_stub_targets = []
for _mod in _absent_cv_mods:
    try:
        __import__(_mod)
    except ImportError:
        _stub_targets.append(_mod)

for _mod in _stub_targets:
    sys.modules[_mod] = MagicMock()

# Stub estimation module if cv2/mediapipe are absent (estimation imports them at top-level)
if _stub_targets:
    _est_stub = MagicMock()
    _est_stub.BodyNotDetectedError = type("BodyNotDetectedError", (Exception,), {})
    _est_stub.LandmarkOccludedError = type("LandmarkOccludedError", (Exception,), {})
    _est_stub.EstimationTimeoutError = type("EstimationTimeoutError", (Exception,), {})
    sys.modules["app.modules.measurements.estimation"] = _est_stub

# Stub measurements.service if needed (it creates an async engine at module level
# using DATABASE_URL which is not configured in the test environment)
if "app.modules.measurements.estimation" in sys.modules:
    from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession
    from sqlalchemy.ext.asyncio import async_sessionmaker as _async_sessionmaker
    from sqlalchemy.ext.asyncio import create_async_engine as _create_async_engine
    from sqlalchemy.pool import StaticPool as _StaticPool

    _test_engine_for_br = _create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=_StaticPool,
    )
    _AsyncSessionFactory_stub = _async_sessionmaker(
        bind=_test_engine_for_br,
        class_=_AsyncSession,
        expire_on_commit=False,
    )
    _svc_stub = MagicMock()
    _svc_stub.AsyncSessionFactory = _AsyncSessionFactory_stub
    sys.modules["app.modules.measurements.service"] = _svc_stub
# ─────────────────────────────────────────────────────────────────────────

import asyncio
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

import app.modules.business_rules.service as br_service
from app.modules.business_rules.dependencies import get_current_user, get_db
from app.modules.business_rules.router import router
from app.modules.auth_catalogues.models import Base as AuthBase
from app.modules.business_rules.models import Base as BRBase
from app.modules.measurements.models import Base as MeasBase

# ---------------------------------------------------------------------------
# Shared test user
# ---------------------------------------------------------------------------

TEST_USER_ID = uuid.uuid4()

# ---------------------------------------------------------------------------
# In-memory SQLite engine
# ---------------------------------------------------------------------------

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def engine():
    eng = create_async_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with eng.begin() as conn:
        await conn.run_sync(MeasBase.metadata.create_all)
        await conn.run_sync(AuthBase.metadata.create_all)
        await conn.run_sync(BRBase.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture(scope="session")
def session_factory(engine):
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture()
async def db_session(session_factory, engine):
    async with session_factory() as session:
        yield session
        await session.rollback()
        all_tables = (
            list(MeasBase.metadata.sorted_tables)
            + list(AuthBase.metadata.sorted_tables)
            + list(BRBase.metadata.sorted_tables)
        )
        async with engine.begin() as conn:
            for table in reversed(all_tables):
                await conn.execute(text(f"DELETE FROM {table.name}"))


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

async def seed_session(db: AsyncSession, user_id: uuid.UUID, status: str = "success") -> uuid.UUID:
    from app.modules.measurements.models import CaptureSession
    session_id = uuid.uuid4()
    cs = CaptureSession(
        id=session_id,
        user_id=user_id,
        status=status,
        is_active=True,
    )
    db.add(cs)
    await db.flush()
    return session_id


async def seed_raw_measurement(
    db: AsyncSession,
    session_id: uuid.UUID,
    bust: float = 87.5,
    waist: float = 68.0,
    hips: float = 93.0,
) -> None:
    from app.modules.measurements.models import RawMeasurement, BodyShape
    result = await db.execute(text("SELECT code FROM body_shapes WHERE code='RECTANGLE'"))
    if result.fetchone() is None:
        db.add(BodyShape(code="RECTANGLE", name="Rectangle"))
        await db.flush()
    rm = RawMeasurement(
        session_id=session_id,
        bust_cm=Decimal(str(bust)),
        waist_cm=Decimal(str(waist)),
        hips_cm=Decimal(str(hips)),
        silhouette_code="RECTANGLE",
    )
    db.add(rm)
    await db.flush()


async def seed_fabric(
    db: AsyncSession,
    fabric_id: uuid.UUID | None = None,
    name: str = "Pagne Wax",
    rigidity: str = "rigid",
) -> uuid.UUID:
    from app.modules.auth_catalogues.models import FabricCategory, Fabric
    cat_id = uuid.uuid4()
    cat = FabricCategory(
        category_id=cat_id,
        category_name=f"Cat-{cat_id.hex[:6]}",
        reference_rigidity_level=rigidity,
    )
    db.add(cat)
    await db.flush()

    fid = fabric_id or uuid.uuid4()
    fab = Fabric(
        fabric_id=fid,
        fabric_name=name,
        fabric_elasticity_rate=Decimal("50.00"),
        fabric_weight=Decimal("200.00"),
        fabric_unit_price=Decimal("10.00"),
        category_id=cat_id,
    )
    db.add(fab)
    await db.flush()
    return fid


# ---------------------------------------------------------------------------
# SQLite-compatible replacements for service helpers
# ---------------------------------------------------------------------------

async def _sqlite_load_fabric_or_raise(fabric_id: uuid.UUID, db: AsyncSession):
    from fastapi import HTTPException, status
    from app.modules.auth_catalogues.models import Fabric
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    stmt = (
        select(Fabric)
        .where(Fabric.fabric_id == fabric_id)
        .options(selectinload(Fabric.category))
    )
    result = await db.execute(stmt)
    fabric = result.scalars().first()

    if fabric is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tissu introuvable dans le catalogue.",
        )
    elasticity_category = fabric.category.reference_rigidity_level if fabric.category else None
    return fabric.fabric_name, elasticity_category


async def _sqlite_upsert_adjustment(session_id, fabric_id, raw, output, db):
    from sqlalchemy import select
    stmt = select(br_service.MeasurementAdjustment).where(
        br_service.MeasurementAdjustment.session_id == session_id,
        br_service.MeasurementAdjustment.fabric_id  == fabric_id,
    )
    result = await db.execute(stmt)
    existing = result.scalars().first()

    if existing is not None:
        existing.raw_bust_cm   = Decimal(str(raw.bust_cm))
        existing.raw_waist_cm  = Decimal(str(raw.waist_cm))
        existing.raw_hips_cm   = Decimal(str(raw.hips_cm))
        existing.bust_ease_cm  = Decimal(str(output.bust.ease_cm))
        existing.waist_ease_cm = Decimal(str(output.waist.ease_cm))
        existing.hips_ease_cm  = Decimal(str(output.hips.ease_cm))
        existing.adjusted_bust_cm  = Decimal(str(output.bust.adjusted_cm))
        existing.adjusted_waist_cm = Decimal(str(output.waist.adjusted_cm))
        existing.adjusted_hips_cm  = Decimal(str(output.hips.adjusted_cm))
        existing.ease_source = output.ease_source
        await db.flush()
        return existing, False
    else:
        from app.modules.business_rules.models import MeasurementAdjustment
        adj = MeasurementAdjustment(
            session_id=session_id,
            fabric_id=fabric_id,
            raw_bust_cm   = Decimal(str(raw.bust_cm)),
            raw_waist_cm  = Decimal(str(raw.waist_cm)),
            raw_hips_cm   = Decimal(str(raw.hips_cm)),
            bust_ease_cm  = Decimal(str(output.bust.ease_cm)),
            waist_ease_cm = Decimal(str(output.waist.ease_cm)),
            hips_ease_cm  = Decimal(str(output.hips.ease_cm)),
            adjusted_bust_cm  = Decimal(str(output.bust.adjusted_cm)),
            adjusted_waist_cm = Decimal(str(output.waist.adjusted_cm)),
            adjusted_hips_cm  = Decimal(str(output.hips.adjusted_cm)),
            ease_source = output.ease_source,
        )
        db.add(adj)
        await db.flush()
        return adj, True


# ---------------------------------------------------------------------------
# FastAPI TestClient fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(db_session):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/ease")

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return TEST_USER_ID

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with (
        patch.object(br_service, "_load_fabric_or_raise", _sqlite_load_fabric_or_raise),
        patch.object(br_service, "_upsert_adjustment",    _sqlite_upsert_adjustment),
    ):
        with TestClient(app, raise_server_exceptions=True) as tc:
            yield tc
