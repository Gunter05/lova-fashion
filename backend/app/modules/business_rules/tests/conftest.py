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

TEST_USER_ID = uuid.UUID("aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa")

# ---------------------------------------------------------------------------
# In-memory SQLite engine
# ---------------------------------------------------------------------------

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _patch_br_constraints_for_sqlite():
    """
    SQLite does not support PostgreSQL-specific SQL functions such as
    char_length().  Strip any CheckConstraints from BRBase tables that
    reference char_length before running CREATE TABLE on SQLite.

    This is called once before the session-scoped engine fixture creates
    all tables.  It mutates the in-process Table metadata in place; the
    production PostgreSQL path is not affected (different process).
    """
    from sqlalchemy import CheckConstraint
    from app.modules.business_rules.models import CompatibilityRule

    table = CompatibilityRule.__table__
    bad_constraints = [
        c for c in list(table.constraints)
        if isinstance(c, CheckConstraint) and "char_length" in str(c.sqltext)
    ]
    for c in bad_constraints:
        table.constraints.discard(c)


def _create_all_tables(conn):
    """
    Create all tables from all three metadata objects in dependency order.

    BRBase models have cross-metadata FKs to tables in MeasBase
    (capture_sessions) and app.database.Base (critical_zone, model).
    SQLAlchemy cannot resolve these FKs during DDL compilation because
    the target tables are in different metadata objects.

    The fix: after creating MeasBase and AuthBase tables, reflect the
    already-existing tables into BRBase.metadata so SQLAlchemy can
    resolve the FK references when it compiles CREATE TABLE for BRBase.
    """
    # Remove PostgreSQL-only constraints that SQLite cannot compile
    _patch_br_constraints_for_sqlite()

    # Step 1 — create measurement tables (defines capture_sessions)
    MeasBase.metadata.create_all(conn)

    # Step 2 — create auth/catalogue tables (defines critical_zone, model)
    AuthBase.metadata.create_all(conn)

    # Step 3 — reflect the cross-metadata FK targets into BRBase's metadata
    # so SQLAlchemy can resolve FKs when compiling BRBase CREATE TABLE DDL.
    from sqlalchemy import Table, MetaData
    for table_name in ("capture_sessions", "critical_zone", "model",
                       "model_morphology", "measurement_adjustments"):
        if table_name not in BRBase.metadata.tables:
            # Find this table in one of the other metadata objects
            for meta in (MeasBase.metadata, AuthBase.metadata):
                if table_name in meta.tables:
                    # Copy the table definition into BRBase.metadata under the same name
                    src = meta.tables[table_name]
                    src.tometadata(BRBase.metadata)
                    break

    # Step 4 — create business_rules tables (can now resolve FKs)
    BRBase.metadata.create_all(conn)


@pytest.fixture(scope="session")
async def engine():
    eng = create_async_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with eng.begin() as conn:
        await conn.run_sync(_create_all_tables)
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

async def _sqlite_load_session_or_raise(
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
):
    """
    SQLite-compatible version of _load_session_or_raise.

    Uses an ORM SELECT instead of db.get() to avoid the greenlet context
    mismatch that occurs when TestClient (synchronous) runs FastAPI handlers
    in a worker thread while the db_session lives in the test's async loop.
    db.get() re-fetches the row in a raw SQLite context and may return the
    user_id as a 32-char hex string; a SELECT via execute() goes through the
    full SQLAlchemy type processor pipeline and always returns uuid.UUID.
    """
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "SQLITE_LOAD_SESSION called: session_id=%s user_id=%s", session_id, user_id
    )
    from fastapi import HTTPException, status
    from sqlalchemy import select
    from app.modules.measurements.models import CaptureSession

    stmt = select(CaptureSession).where(CaptureSession.id == session_id)
    result = await db.execute(stmt)
    session = result.scalars().first()

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} introuvable.",
        )

    def _to_uuid(v) -> uuid.UUID:
        return v if isinstance(v, uuid.UUID) else uuid.UUID(str(v))

    _logging.getLogger(__name__).warning(
        "SQLITE_LOAD_SESSION db result: session.user_id=%r user_id=%r match=%s",
        session.user_id, user_id,
        _to_uuid(session.user_id) == _to_uuid(user_id),
    )
    if _to_uuid(session.user_id) != _to_uuid(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous n'êtes pas autorisé à accéder à cette session.",
        )

    return session


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
        patch.object(br_service, "_load_session_or_raise", _sqlite_load_session_or_raise),
        patch.object(br_service, "_load_fabric_or_raise", _sqlite_load_fabric_or_raise),
        patch.object(br_service, "_upsert_adjustment",    _sqlite_upsert_adjustment),
    ):
        with TestClient(app, raise_server_exceptions=True) as tc:
            yield tc


# ---------------------------------------------------------------------------
# Module 6 — Compatibility Engine seed helpers
# ---------------------------------------------------------------------------
# NOTE: The new Module 6 ORM models (CompatibilityRule, ModelMorphology,
# VerdictEvaluation, RiskZone) all share BRBase (business_rules/models.py).
# The existing `_create_all_tables` helper above already includes
# `BRBase.metadata.sorted_tables`, so those tables are created automatically
# by the session-scoped `engine` fixture — no duplicate create_all needed.
# ---------------------------------------------------------------------------


async def seed_compatibility_rule(
    db: AsyncSession,
    cut_type: str,
    fabric_property: str,
    zone_name: str,
    condition: str,
    severity: str,
    explanation: str,
    admin_id: uuid.UUID,
) -> "CompatibilityRule":
    """
    Insert a CompatibilityRule row for the given (cut_type, fabric_property, zone_name).

    The zone_name is resolved to a CriticalZone.zone_id via a SELECT; if no
    matching zone exists yet it is created on-the-fly.  The caller may pass
    zone_name="" or zone_name=None to leave zone_id NULL (global rule).
    """
    from sqlalchemy import select
    from app.modules.business_rules.models import CompatibilityRule
    from app.modules.auth_catalogues.models import CriticalZone

    zone_id = None
    if zone_name:
        result = await db.execute(
            select(CriticalZone).where(CriticalZone.zone_name == zone_name)
        )
        zone_obj = result.scalars().first()
        if zone_obj is None:
            zone_obj = CriticalZone(zone_id=uuid.uuid4(), zone_name=zone_name)
            db.add(zone_obj)
            await db.flush()
        zone_id = zone_obj.zone_id

    rule = CompatibilityRule(
        cut_type=cut_type,
        fabric_property=fabric_property,
        zone_id=zone_id,
        mathematical_condition=condition,
        severity_level=severity,
        explanation_message=explanation,
        is_active=True,
        version=1,
        admin_id=admin_id,
    )
    db.add(rule)
    await db.flush()
    return rule


async def seed_model(
    db: AsyncSession,
    cut_type: str = "Fitted",
    status: str = "Published",
) -> "Model":
    """
    Insert a minimal Model row plus three CriticalZone rows (bust, waist, hips)
    linked via the model_critical_zone association table.

    Returns the created Model ORM instance (with .zones populated after flush).
    """
    from sqlalchemy import select, insert
    from app.modules.auth_catalogues.models import (
        Model,
        CriticalZone,
        GarmentTypeEnum,
        CutTypeEnum,
        ModelStatusEnum,
        model_critical_zone_table,
    )

    # Resolve enum values — SQLite stores them as plain strings, so pass
    # the string value rather than the Python enum member.
    cut_type_val = CutTypeEnum(cut_type)
    status_val = ModelStatusEnum(status)

    model_id = uuid.uuid4()
    m = Model(
        model_id=model_id,
        model_name=f"Model-{model_id.hex[:6]}",
        photo_url="https://placeholder.test/photo.jpg",
        garment_type=GarmentTypeEnum.Dress,
        cut_type=cut_type_val,
        status=status_val,
        creator_id=uuid.uuid4(),
    )
    db.add(m)
    await db.flush()

    # Ensure the three standard zones exist and link them to the model
    zone_names = ["bust", "waist", "hips"]
    for zname in zone_names:
        result = await db.execute(
            select(CriticalZone).where(CriticalZone.zone_name == zname)
        )
        zone_obj = result.scalars().first()
        if zone_obj is None:
            zone_obj = CriticalZone(zone_id=uuid.uuid4(), zone_name=zname)
            db.add(zone_obj)
            await db.flush()

        # Insert into the association table directly (avoid ORM append to
        # prevent duplicate-key errors when the zone already exists globally)
        existing_link = await db.execute(
            select(model_critical_zone_table).where(
                model_critical_zone_table.c.model_id == model_id,
                model_critical_zone_table.c.zone_id == zone_obj.zone_id,
            )
        )
        if existing_link.fetchone() is None:
            await db.execute(
                insert(model_critical_zone_table).values(
                    model_id=model_id, zone_id=zone_obj.zone_id
                )
            )

    await db.flush()
    return m


async def seed_model_morphology(
    db: AsyncSession,
    model_id: uuid.UUID,
    morphology_id: uuid.UUID,
    score: str,
) -> None:
    """
    Insert a ModelMorphology row linking a Model to a body morphology
    with the given suitability score ('Ideal' | 'Flattering' | 'Avoid').
    """
    from app.modules.business_rules.models import ModelMorphology

    mm = ModelMorphology(
        model_id=model_id,
        morphology_id=morphology_id,
        suitability_score=score,
    )
    db.add(mm)
    await db.flush()


async def seed_model_fabric_link(
    db: AsyncSession,
    model_id: uuid.UUID,
    fabric_id: uuid.UUID,
    level: str = "Recommended",
) -> None:
    """
    Insert a ModelFabric association row linking a Model to a Fabric.

    The `level` parameter is accepted for API consistency with the task spec
    but is not stored in the ModelFabric ORM model (which has no level column).
    """
    from app.modules.auth_catalogues.models import ModelFabric

    mf = ModelFabric(
        model_id=model_id,
        fabric_id=fabric_id,
    )
    db.add(mf)
    await db.flush()


async def seed_verdict_evaluation(
    db: AsyncSession,
    evaluation_id: uuid.UUID,
    client_id: uuid.UUID,
    model_id: uuid.UUID,
    fabric_id: uuid.UUID,
    measurements_id: uuid.UUID,
    morphology_id: uuid.UUID,
    global_status: str,
    risk_zones: list | None = None,
) -> "VerdictEvaluation":
    """
    Insert a VerdictEvaluation row (and optional RiskZone child rows) for use
    in read-endpoint integration tests.

    Parameters
    ----------
    evaluation_id    : fixed UUID so callers can assert on it in GET responses
    client_id        : UUID of the requesting client
    model_id         : must reference an existing Model row
    fabric_id        : logical FK (no ORM-level FK constraint in this table)
    measurements_id  : must reference an existing MeasurementAdjustment row
    morphology_id    : logical FK (no ORM-level FK constraint)
    global_status    : one of Compatible / Compatible_with_Reservations /
                       Incompatible / Indeterminate / Failed
    risk_zones       : list of dicts accepted by RiskZone(**rz_dict); each must
                       include calculated_variance, localized_verdict, explanation,
                       rule_version; rule_id and zone_id are optional (nullable)
    """
    from app.modules.business_rules.models import VerdictEvaluation, RiskZone

    evaluation = VerdictEvaluation(
        evaluation_id=evaluation_id,
        client_id=client_id,
        model_id=model_id,
        fabric_id=fabric_id,
        measurements_id=measurements_id,
        morphology_id=morphology_id,
        global_status=global_status,
    )
    db.add(evaluation)
    await db.flush()

    for rz_dict in (risk_zones or []):
        rz = RiskZone(
            evaluation_id=evaluation_id,
            **rz_dict,
        )
        db.add(rz)

    await db.flush()
    return evaluation


# ---------------------------------------------------------------------------
# Module 6 — SQLite-compatible replacements for raw-SQL service helpers
# ---------------------------------------------------------------------------
# The production helpers use raw SQL with UUID parameters as str(uuid) which
# includes hyphens (e.g. '550e8400-e29b-41d4-a716-446655440000').
# SQLite stores UUIDs via SQLAlchemy's UUID(as_uuid=True) as 32-char hex
# strings WITHOUT hyphens (value.hex), so the WHERE clause never matches.
# These replacements pass uuid.hex to the raw SQL queries.
# ---------------------------------------------------------------------------


async def _sqlite_load_fabric_or_422(
    fabric_id: uuid.UUID,
    db: AsyncSession,
):
    """
    SQLite-compatible version of _load_fabric_or_422.
    Passes fabric_id.hex (no hyphens) so the WHERE clause matches.
    """
    from fastapi import HTTPException, status
    from sqlalchemy import text

    sql = text(
        """
        SELECT
            f.fabric_id,
            f.fabric_name,
            f.fabric_status,
            fc.reference_rigidity_level
        FROM fabrics f
        LEFT JOIN fabric_categories fc ON fc.category_id = f.category_id
        WHERE f.fabric_id = :fabric_id
        """
    )
    result = await db.execute(sql, {"fabric_id": fabric_id.hex})
    row = result.mappings().first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Tissu {fabric_id} introuvable dans le catalogue.",
        )

    if row["fabric_status"] != "available":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Le tissu n'est pas disponible. "
                f"Statut actuel: '{row['fabric_status']}'."
            ),
        )

    fabric_property: str = row["reference_rigidity_level"] or "rigid"
    return row, fabric_property


async def _sqlite_load_morphology_or_422(
    morphology_id: uuid.UUID,
    db: AsyncSession,
):
    """
    SQLite-compatible version of _load_morphology_or_422.
    body_shapes.code is a String PK, so we query str(morphology_id) directly.
    This helper exists to ensure consistent behaviour across both UUID formats.
    """
    from fastapi import HTTPException, status
    from sqlalchemy import text

    sql = text("SELECT code FROM body_shapes WHERE code = :morphology_id")
    result = await db.execute(sql, {"morphology_id": str(morphology_id)})
    row = result.mappings().first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Morphologie {morphology_id} introuvable.",
        )
    return row


async def _sqlite_load_active_rules(
    cut_type: str,
    fabric_property: str,
    db: AsyncSession,
):
    """
    SQLite-compatible version of _load_active_rules.
    The SQL logic is identical; included here for symmetry.
    """
    from sqlalchemy import text
    from fastapi import HTTPException, status
    from app.modules.business_rules.engine import RuleRecord
    import logging

    logger = logging.getLogger(__name__)

    sql = text(
        """
        SELECT cr.rule_id,
               cr.zone_id,
               cr.cut_type,
               cr.fabric_property,
               cr.mathematical_condition,
               cr.severity_level,
               cr.explanation_message,
               cr.version,
               COALESCE(cz.zone_name, CAST(cr.zone_id AS TEXT)) AS zone_name
        FROM compatibility_rules cr
        INNER JOIN (
            SELECT zone_id, MAX(version) AS max_version
            FROM compatibility_rules
            WHERE cut_type = :cut_type
              AND fabric_property = :fabric_property
              AND is_active = 1
            GROUP BY zone_id
        ) latest ON cr.zone_id = latest.zone_id
               AND cr.version = latest.max_version
        LEFT JOIN critical_zone cz ON cz.zone_id = cr.zone_id
        WHERE cr.cut_type = :cut_type
          AND cr.fabric_property = :fabric_property
          AND cr.is_active = 1
        """
    )
    try:
        result = await db.execute(
            sql, {"cut_type": cut_type, "fabric_property": fabric_property}
        )
        rows = result.mappings().all()
    except Exception as exc:
        logger.error("DB error loading active rules: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur technique lors du chargement des règles de compatibilité.",
        ) from exc

    return [
        RuleRecord(
            rule_id=row["rule_id"],
            zone_id=row["zone_id"],
            zone_name=row["zone_name"] or "",
            mathematical_condition=row["mathematical_condition"],
            severity_level=row["severity_level"],
            explanation_message=row["explanation_message"],
            version=row["version"],
        )
        for row in rows
    ]


async def _sqlite_check_fabric_link(
    model_id: uuid.UUID,
    fabric_id: uuid.UUID,
    db: AsyncSession,
):
    """
    SQLite-compatible version of _check_fabric_link.
    Passes hex UUIDs to the raw SQL query.
    """
    from fastapi import HTTPException, status
    from sqlalchemy import text
    from app.modules.business_rules.engine import RiskZoneDict
    import logging

    logger = logging.getLogger(__name__)

    sql = text(
        """
        SELECT fabric_id
        FROM model_fabric
        WHERE model_id = :model_id
          AND fabric_id = :fabric_id
        """
    )
    try:
        result = await db.execute(
            sql, {"model_id": model_id.hex, "fabric_id": fabric_id.hex}
        )
        row = result.mappings().first()
    except Exception as exc:
        logger.error("DB error checking fabric link: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur technique lors de la vérification du tissu.",
        ) from exc

    if row is not None:
        return "Accepted", None

    fabric_risk = RiskZoneDict(
        rule_id=None,
        zone_id=None,
        calculated_variance=0.0,
        localized_verdict="Reserve",
        explanation=(
            "Fabric not listed as compatible with this model by the administrator"
        ),
        rule_version=0,
        warnings=[],
    )
    return None, fabric_risk


async def _sqlite_check_morphology_link(
    model_id: uuid.UUID,
    morphology_id: uuid.UUID,
    db: AsyncSession,
):
    """
    SQLite-compatible version of _check_morphology_link.
    Passes hex UUIDs for the model_morphology query.
    model_morphology.morphology_id is stored as hex by SQLAlchemy.
    """
    from fastapi import HTTPException, status
    from sqlalchemy import text
    import logging

    logger = logging.getLogger(__name__)

    sql = text(
        """
        SELECT suitability_score
        FROM model_morphology
        WHERE model_id = :model_id
          AND morphology_id = :morphology_id
        """
    )
    try:
        result = await db.execute(
            sql, {"model_id": model_id.hex, "morphology_id": morphology_id.hex}
        )
        row = result.mappings().first()
    except Exception as exc:
        logger.error("DB error checking morphology link: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur technique lors de la vérification de la morphologie.",
        ) from exc

    return row["suitability_score"] if row else None


async def _sqlite_load_model_or_422(
    model_id: uuid.UUID,
    db: AsyncSession,
):
    """
    SQLite-compatible version of _load_model_or_422.
    Explicitly refreshes the model and its zones after loading so
    that the async session has no expired lazy-load attributes.
    """
    from fastapi import HTTPException, status
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.modules.auth_catalogues.models import Model, ModelStatusEnum, CriticalZone

    stmt = (
        select(Model)
        .where(Model.model_id == model_id)
        .options(selectinload(Model.zones))
    )
    result = await db.execute(stmt)
    model = result.scalars().first()

    if model is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Modèle {model_id} introuvable.",
        )

    if model.status != ModelStatusEnum.Published:
        current = model.status.value if hasattr(model.status, "value") else str(model.status)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Le modèle n'est pas publié. "
                f"Statut actuel: '{current}'."
            ),
        )

    return model


async def _sqlite_persist_evaluation(
    eval_data: dict,
    risk_zones,
    db: AsyncSession,
):
    """
    SQLite-compatible version of _persist_evaluation.

    The production version calls `async with db.begin()` which fails
    when SQLAlchemy's autobegin has already started a transaction
    (e.g. after operations in the same test session).

    This version uses `begin_nested()` (SAVEPOINT) so it works inside
    an already-active transaction, as is the case in all M6 tests.

    After the savepoint commits, the ORM object's relationships are expired.
    We explicitly reload the evaluation with selectin-loaded risk_zones so
    that VerdictEvaluationResponse.model_validate() can access them without
    triggering a greenlet IO error.
    """
    import logging
    from fastapi import HTTPException, status
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import selectinload
    from app.modules.business_rules.models import VerdictEvaluation, RiskZone

    logger = logging.getLogger(__name__)

    for attempt in range(2):
        try:
            evaluation_id = eval_data.get("evaluation_id") or uuid.uuid4()
            async with db.begin_nested():
                evaluation = VerdictEvaluation(**{**eval_data, "evaluation_id": evaluation_id})
                db.add(evaluation)
                await db.flush()

                for rz in risk_zones:
                    # SQLite raw-SQL queries return UUIDs as hex strings (no
                    # hyphens).  UUID(as_uuid=True) columns require uuid.UUID
                    # objects, so coerce str → UUID when necessary.
                    def _to_uuid_or_none(v):
                        if v is None:
                            return None
                        if isinstance(v, uuid.UUID):
                            return v
                        try:
                            return uuid.UUID(str(v))
                        except (ValueError, AttributeError):
                            return None

                    db.add(
                        RiskZone(
                            evaluation_id=evaluation.evaluation_id,
                            rule_id=_to_uuid_or_none(rz.rule_id),
                            zone_id=_to_uuid_or_none(rz.zone_id),
                            calculated_variance=rz.calculated_variance,
                            localized_verdict=rz.localized_verdict,
                            explanation=rz.explanation,
                            rule_version=rz.rule_version,
                        )
                    )
            # Savepoint committed — reload with eager risk_zones to avoid
            # greenlet IO error when model_validate accesses the relationship.
            result = await db.execute(
                select(VerdictEvaluation)
                .where(VerdictEvaluation.evaluation_id == evaluation_id)
                .options(selectinload(VerdictEvaluation.risk_zones))
            )
            return result.scalars().first()

        except IntegrityError as exc:
            if attempt == 0 and "evaluation_id" in str(exc).lower():
                logger.warning("UUID collision on evaluation_id — retrying with new UUID")
                eval_data = {**eval_data, "evaluation_id": uuid.uuid4()}
                continue
            logger.error("Persistence IntegrityError: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur de persistance de l'évaluation (contrainte d'intégrité).",
            ) from exc
        except Exception as exc:
            logger.error("Persistence error: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de la persistance de l'évaluation.",
            ) from exc

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Impossible de persister l'évaluation après deux tentatives.",
    )
