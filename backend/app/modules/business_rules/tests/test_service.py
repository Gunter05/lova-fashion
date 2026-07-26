"""
Integration tests for Module 5 — Ease Allowance Calculation Engine.

Tests exercise the HTTP endpoints via FastAPI TestClient + in-memory SQLite.
PostgreSQL-specific constructs (pg_insert upsert) are patched to a pure-Python
equivalent at the service layer so the tests remain self-contained.

Coverage:
    S1  — POST /adjustments: 201 for new record             (AC-01.5)
    S2  — POST /adjustments: 200 on recompute (upsert)      (AC-01.6)
    S3  — POST /adjustments: 424 when no raw measurement    (AC-01.3)
    S4  — POST /adjustments: 404 when fabric not found      (AC-01.4)
    S5  — POST /adjustments: correct adjusted values        (US-02, US-03)
    S6  — GET /adjustments/{id}: 200 + full detail          (AC-05.1)
    S7  — GET /adjustments/{id}: 404 for unknown id         (AC-05.2)
    S8  — GET /sessions/{id}/adjustments: list, newest first (AC-06.1)
    S9  — GET /sessions/{id}/adjustments: empty list        (AC-06.2)
    S10 — ease_source == "rule" for known category          (AC-02.1)
    S11 — ease_source == "default_fallback" for unknown cat (AC-02.4)
    S12 — adjusted values clamped ≥ 0                       (AC-04.1)
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

import app.modules.business_rules.service as br_service
from app.modules.business_rules.models import MeasurementAdjustment
from app.modules.business_rules.tests.conftest import (
    TEST_USER_ID,
    seed_fabric,
    seed_raw_measurement,
    seed_session,
    _sqlite_load_fabric_or_raise,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _adj_url(session_id, fabric_id):
    return "/api/v1/ease/adjustments"


def _post_adjustment(client, session_id, fabric_id):
    return client.post(
        "/api/v1/ease/adjustments",
        json={"session_id": str(session_id), "fabric_id": str(fabric_id)},
    )


# ---------------------------------------------------------------------------
# Upsert patch — replaces pg_insert (PostgreSQL-only) with a pure Python upsert
# ---------------------------------------------------------------------------

async def _sqlite_upsert_adjustment(session_id, fabric_id, raw, output, db):
    """
    SQLite-compatible upsert: check for existing row, insert or update.
    Mirrors the semantics of the PostgreSQL ON CONFLICT DO UPDATE.
    """
    from sqlalchemy import select
    stmt = select(MeasurementAdjustment).where(
        MeasurementAdjustment.session_id == session_id,
        MeasurementAdjustment.fabric_id == fabric_id,
    )
    result = await db.execute(stmt)
    existing = result.scalars().first()

    if existing is not None:
        # Overwrite
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
# Full patch context for service-level functions
# ---------------------------------------------------------------------------

from contextlib import asynccontextmanager
from unittest.mock import patch


def _full_patch():
    """Return a context that patches both pg_insert helpers with SQLite versions."""
    p1 = patch.object(br_service, "_upsert_adjustment", _sqlite_upsert_adjustment)
    p2 = patch.object(br_service, "_load_fabric_or_raise", _sqlite_load_fabric_or_raise)
    return p1, p2


# ---------------------------------------------------------------------------
# S1 — New adjustment returns 201
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_s1_new_adjustment_returns_201(client, db_session):
    sid = await seed_session(db_session, TEST_USER_ID)
    await seed_raw_measurement(db_session, sid)
    fid = await seed_fabric(db_session, rigidity="rigid")
    await db_session.commit()

    with patch.object(br_service, "_upsert_adjustment", _sqlite_upsert_adjustment):
        resp = _post_adjustment(client, sid, fid)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["ease_source"] == "rule"
    assert body["bust"]["ease_cm"] == 4.0


# ---------------------------------------------------------------------------
# S2 — Re-computing the same (session, fabric) returns 200
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_s2_recompute_returns_200(client, db_session):
    sid = await seed_session(db_session, TEST_USER_ID)
    await seed_raw_measurement(db_session, sid)
    fid = await seed_fabric(db_session, rigidity="semi-stretch")
    await db_session.commit()

    with patch.object(br_service, "_upsert_adjustment", _sqlite_upsert_adjustment):
        first  = _post_adjustment(client, sid, fid)
        second = _post_adjustment(client, sid, fid)

    assert first.status_code  == 201
    assert second.status_code == 200


# ---------------------------------------------------------------------------
# S3 — 424 when no raw measurement exists
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_s3_no_raw_measurement_returns_424(client, db_session):
    sid = await seed_session(db_session, TEST_USER_ID)
    fid = await seed_fabric(db_session)
    await db_session.commit()

    with patch.object(br_service, "_upsert_adjustment", _sqlite_upsert_adjustment):
        resp = _post_adjustment(client, sid, fid)

    assert resp.status_code == 424


# ---------------------------------------------------------------------------
# S4 — 404 when fabric not found
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_s4_fabric_not_found_returns_404(client, db_session):
    sid = await seed_session(db_session, TEST_USER_ID)
    await seed_raw_measurement(db_session, sid)
    await db_session.commit()

    nonexistent_fabric = uuid.uuid4()
    with patch.object(br_service, "_upsert_adjustment", _sqlite_upsert_adjustment):
        resp = _post_adjustment(client, sid, nonexistent_fabric)

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# S5 — Correct adjusted values for rigid fabric
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_s5_correct_adjusted_values_rigid(client, db_session):
    """AC-02.1 : rigid → +4 cm on all zones."""
    sid = await seed_session(db_session, TEST_USER_ID)
    await seed_raw_measurement(db_session, sid, bust=87.5, waist=68.0, hips=93.0)
    fid = await seed_fabric(db_session, rigidity="rigid")
    await db_session.commit()

    with patch.object(br_service, "_upsert_adjustment", _sqlite_upsert_adjustment):
        resp = _post_adjustment(client, sid, fid)

    assert resp.status_code == 201
    body = resp.json()
    assert body["bust"]["adjusted_cm"]  == 91.5
    assert body["waist"]["adjusted_cm"] == 72.0
    assert body["hips"]["adjusted_cm"]  == 97.0


# ---------------------------------------------------------------------------
# S6 — GET /adjustments/{id}: 200 + full detail
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_s6_get_adjustment_detail(client, db_session):
    sid = await seed_session(db_session, TEST_USER_ID)
    await seed_raw_measurement(db_session, sid)
    fid = await seed_fabric(db_session)
    await db_session.commit()

    with patch.object(br_service, "_upsert_adjustment", _sqlite_upsert_adjustment):
        post_resp = _post_adjustment(client, sid, fid)
    assert post_resp.status_code == 201
    adj_id = post_resp.json()["adjustment_id"]

    get_resp = client.get(f"/api/v1/ease/adjustments/{adj_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["adjustment_id"] == adj_id
    assert "bust" in body and "waist" in body and "hips" in body


# ---------------------------------------------------------------------------
# S7 — GET /adjustments/{id}: 404 for unknown id
# ---------------------------------------------------------------------------

def test_s7_get_unknown_adjustment_returns_404(client):
    fake_id = uuid.uuid4()
    resp = client.get(f"/api/v1/ease/adjustments/{fake_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# S8 — List adjustments for a session, newest first
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_s8_list_adjustments_ordered(client, db_session):
    sid = await seed_session(db_session, TEST_USER_ID)
    await seed_raw_measurement(db_session, sid)
    fid1 = await seed_fabric(db_session, name="Fabric A", rigidity="rigid")
    fid2 = await seed_fabric(db_session, name="Fabric B", rigidity="stretch")
    await db_session.commit()

    with patch.object(br_service, "_upsert_adjustment", _sqlite_upsert_adjustment):
        _post_adjustment(client, sid, fid1)
        _post_adjustment(client, sid, fid2)

    resp = client.get(f"/api/v1/ease/sessions/{sid}/adjustments")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["adjustments"]) == 2


# ---------------------------------------------------------------------------
# S9 — Empty list when no adjustments
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_s9_empty_list(client, db_session):
    sid = await seed_session(db_session, TEST_USER_ID)
    await db_session.commit()

    resp = client.get(f"/api/v1/ease/sessions/{sid}/adjustments")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["adjustments"] == []


# ---------------------------------------------------------------------------
# S10 — ease_source = "rule" for known category
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_s10_ease_source_rule(client, db_session):
    sid = await seed_session(db_session, TEST_USER_ID)
    await seed_raw_measurement(db_session, sid)
    fid = await seed_fabric(db_session, rigidity="stretch")
    await db_session.commit()

    with patch.object(br_service, "_upsert_adjustment", _sqlite_upsert_adjustment):
        resp = _post_adjustment(client, sid, fid)

    assert resp.status_code == 201
    assert resp.json()["ease_source"] == "rule"


# ---------------------------------------------------------------------------
# S11 — ease_source = "default_fallback" for unknown category
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_s11_ease_source_default_fallback(client, db_session):
    """AC-02.4 : unknown rigidity level → default_fallback."""
    sid = await seed_session(db_session, TEST_USER_ID)
    await seed_raw_measurement(db_session, sid)
    fid = await seed_fabric(db_session, rigidity="unknown_type")
    await db_session.commit()

    with patch.object(br_service, "_upsert_adjustment", _sqlite_upsert_adjustment):
        resp = _post_adjustment(client, sid, fid)

    assert resp.status_code == 201
    assert resp.json()["ease_source"] == "default_fallback"


# ---------------------------------------------------------------------------
# S12 — Adjusted values never negative (floor clamp)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_s12_adjusted_values_never_negative(client, db_session):
    """AC-04.1 : even with stretch fabric on small raw values, result ≥ 0."""
    sid = await seed_session(db_session, TEST_USER_ID)
    # Very small measurements — stretch delta (-2) would go below 0 for bust=1
    await seed_raw_measurement(db_session, sid, bust=1.0, waist=1.0, hips=1.0)
    fid = await seed_fabric(db_session, rigidity="stretch")
    await db_session.commit()

    with patch.object(br_service, "_upsert_adjustment", _sqlite_upsert_adjustment):
        resp = _post_adjustment(client, sid, fid)

    assert resp.status_code == 201
    body = resp.json()
    assert body["bust"]["adjusted_cm"]  >= 0.0
    assert body["waist"]["adjusted_cm"] >= 0.0
    assert body["hips"]["adjusted_cm"]  >= 0.0


# ===========================================================================
# Module 6 — CompatibilityService integration tests
# ===========================================================================
# Tests M6-S1 through M6-S6 exercise CompatibilityService.verify() directly
# (not via HTTP) using the in-memory SQLite session from the db_session fixture.
# Each test seeds all prerequisites, commits, calls verify(), then asserts on
# the returned VerdictEvaluationResponse and the persisted DB rows.
#
# SQLite stores UUID(as_uuid=True) columns as 32-char hex (no hyphens) via
# value.hex.  The production service helpers pass str(uuid) which includes
# hyphens, causing raw-SQL WHERE clauses to miss every row.  We patch the
# three affected helpers with SQLite-compatible equivalents from conftest.
# ===========================================================================

import app.modules.business_rules.service as _br6_service
from app.modules.business_rules.tests.conftest import (
    seed_compatibility_rule,
    seed_model,
    seed_model_fabric_link,
    seed_model_morphology,
    _sqlite_load_fabric_or_422,
    _sqlite_load_active_rules,
    _sqlite_check_fabric_link,
    _sqlite_check_morphology_link,
    _sqlite_load_model_or_422,
    _sqlite_persist_evaluation,
)


def _m6_patches():
    """
    Return the three patches needed to make Module 6 service helpers
    work correctly against in-memory SQLite.
    """
    return [
        patch.object(_br6_service, "_load_fabric_or_422", _sqlite_load_fabric_or_422),
        patch.object(_br6_service, "_load_active_rules", _sqlite_load_active_rules),
        patch.object(_br6_service, "_check_fabric_link", _sqlite_check_fabric_link),
        patch.object(_br6_service, "_check_morphology_link", _sqlite_check_morphology_link),
        patch.object(_br6_service, "_load_model_or_422", _sqlite_load_model_or_422),
        patch.object(_br6_service, "_persist_evaluation", _sqlite_persist_evaluation),
    ]


def _make_adjustment(db_session, adj_id, session_id, fabric_id):
    """
    Helper: insert a MeasurementAdjustment with realistic non-zero adjusted values.
    Returns the inserted MeasurementAdjustment ORM object.
    """
    from decimal import Decimal
    from app.modules.business_rules.models import MeasurementAdjustment

    adj = MeasurementAdjustment(
        id=adj_id,
        session_id=session_id,
        fabric_id=fabric_id,
        raw_bust_cm=Decimal("90.0"),
        raw_waist_cm=Decimal("70.0"),
        raw_hips_cm=Decimal("95.0"),
        bust_ease_cm=Decimal("4.0"),
        waist_ease_cm=Decimal("4.0"),
        hips_ease_cm=Decimal("4.0"),
        adjusted_bust_cm=Decimal("94.0"),
        adjusted_waist_cm=Decimal("74.0"),
        adjusted_hips_cm=Decimal("99.0"),
        ease_source="rule",
    )
    db_session.add(adj)
    return adj


async def _seed_body_shape(db_session, morphology_id):
    """Insert a BodyShape whose code equals str(morphology_id)."""
    from app.modules.measurements.models import BodyShape

    db_session.add(BodyShape(code=str(morphology_id), name="Test Morphology"))
    await db_session.flush()


# ---------------------------------------------------------------------------
# M6-S1 — Compatible: rule never fires → global_status == "Compatible"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m6_s1_compatible(db_session):
    """
    Seed a rule whose condition never fires (value > 9999.0).
    verify() must return global_status="Compatible", risk_zones=[],
    and persist exactly one VerdictEvaluation row.
    """
    from sqlalchemy import select
    from app.modules.business_rules.models import VerdictEvaluation
    from app.modules.business_rules.schemas import VerificationRequest
    from app.modules.business_rules.service import CompatibilityService

    user_id = uuid.uuid4()
    morphology_id = uuid.uuid4()
    adj_id = uuid.uuid4()

    await _seed_body_shape(db_session, morphology_id)

    sid = await seed_session(db_session, user_id)
    await seed_raw_measurement(db_session, sid)
    fid = await seed_fabric(db_session, rigidity="rigid")
    model = await seed_model(db_session, cut_type="Fitted")
    await seed_model_fabric_link(db_session, model.model_id, fid)
    _make_adjustment(db_session, adj_id, sid, fid)

    # Rule that never fires
    await seed_compatibility_rule(
        db_session,
        cut_type="Fitted",
        fabric_property="rigid",
        zone_name="bust",
        condition="value > 9999.0",
        severity="Reserve",
        explanation="Never-fire test rule",
        admin_id=uuid.uuid4(),
    )

    await db_session.commit()

    request = VerificationRequest(
        adjustment_id=adj_id,
        model_id=model.model_id,
        fabric_id=fid,
        morphology_id=morphology_id,
        client_id=user_id,
    )

    patches = _m6_patches()
    for p in patches:
        p.start()
    try:
        result = await CompatibilityService.verify(request, user_id, db_session)
    finally:
        for p in patches:
            p.stop()

    assert result.global_status == "Compatible"
    assert result.risk_zones == []

    # Verify DB persistence
    rows = (await db_session.execute(select(VerdictEvaluation))).scalars().all()
    assert len(rows) == 1
    assert rows[0].global_status == "Compatible"


# ---------------------------------------------------------------------------
# M6-S2 — Compatible_with_Reservations: Reserve rule always fires
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m6_s2_compatible_with_reservations(db_session):
    """
    Seed a Reserve rule whose condition always fires (value > 0.0).
    verify() must return global_status="Compatible_with_Reservations",
    len(risk_zones) == 1, risk_zones[0].localized_verdict == "Reserve",
    and persist both VerdictEvaluation and RiskZone rows.
    """
    from sqlalchemy import select
    from app.modules.business_rules.models import VerdictEvaluation, RiskZone
    from app.modules.business_rules.schemas import VerificationRequest
    from app.modules.business_rules.service import CompatibilityService

    user_id = uuid.uuid4()
    morphology_id = uuid.uuid4()
    adj_id = uuid.uuid4()

    await _seed_body_shape(db_session, morphology_id)

    sid = await seed_session(db_session, user_id)
    await seed_raw_measurement(db_session, sid)
    fid = await seed_fabric(db_session, rigidity="rigid")
    model = await seed_model(db_session, cut_type="Fitted")
    await seed_model_fabric_link(db_session, model.model_id, fid)
    _make_adjustment(db_session, adj_id, sid, fid)

    # Reserve rule that always fires
    await seed_compatibility_rule(
        db_session,
        cut_type="Fitted",
        fabric_property="rigid",
        zone_name="bust",
        condition="value > 0.0",
        severity="Reserve",
        explanation="Always-fire Reserve rule",
        admin_id=uuid.uuid4(),
    )

    await db_session.commit()

    request = VerificationRequest(
        adjustment_id=adj_id,
        model_id=model.model_id,
        fabric_id=fid,
        morphology_id=morphology_id,
        client_id=user_id,
    )

    patches = _m6_patches()
    for p in patches:
        p.start()
    try:
        result = await CompatibilityService.verify(request, user_id, db_session)
    finally:
        for p in patches:
            p.stop()

    assert result.global_status == "Compatible_with_Reservations"
    assert len(result.risk_zones) == 1
    assert result.risk_zones[0].localized_verdict == "Reserve"

    # Verify DB persistence — VerdictEvaluation row
    eval_rows = (await db_session.execute(select(VerdictEvaluation))).scalars().all()
    assert len(eval_rows) == 1
    assert eval_rows[0].global_status == "Compatible_with_Reservations"

    # Verify DB persistence — RiskZone row
    rz_rows = (await db_session.execute(select(RiskZone))).scalars().all()
    assert len(rz_rows) == 1
    assert rz_rows[0].localized_verdict == "Reserve"


# ---------------------------------------------------------------------------
# M6-S3 — Incompatible: Incompatible rule always fires
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m6_s3_incompatible(db_session):
    """
    Seed an Incompatible rule whose condition always fires (value > 0.0).
    verify() must return global_status="Incompatible" and
    risk_zones[0].localized_verdict == "Incompatible".
    """
    from sqlalchemy import select
    from app.modules.business_rules.models import VerdictEvaluation
    from app.modules.business_rules.schemas import VerificationRequest
    from app.modules.business_rules.service import CompatibilityService

    user_id = uuid.uuid4()
    morphology_id = uuid.uuid4()
    adj_id = uuid.uuid4()

    await _seed_body_shape(db_session, morphology_id)

    sid = await seed_session(db_session, user_id)
    await seed_raw_measurement(db_session, sid)
    fid = await seed_fabric(db_session, rigidity="rigid")
    model = await seed_model(db_session, cut_type="Fitted")
    await seed_model_fabric_link(db_session, model.model_id, fid)
    _make_adjustment(db_session, adj_id, sid, fid)

    # Incompatible rule that always fires
    await seed_compatibility_rule(
        db_session,
        cut_type="Fitted",
        fabric_property="rigid",
        zone_name="bust",
        condition="value > 0.0",
        severity="Incompatible",
        explanation="Always-fire Incompatible rule",
        admin_id=uuid.uuid4(),
    )

    await db_session.commit()

    request = VerificationRequest(
        adjustment_id=adj_id,
        model_id=model.model_id,
        fabric_id=fid,
        morphology_id=morphology_id,
        client_id=user_id,
    )

    patches = _m6_patches()
    for p in patches:
        p.start()
    try:
        result = await CompatibilityService.verify(request, user_id, db_session)
    finally:
        for p in patches:
            p.stop()

    assert result.global_status == "Incompatible"
    assert len(result.risk_zones) == 1
    assert result.risk_zones[0].localized_verdict == "Incompatible"

    # Verify DB persistence
    rows = (await db_session.execute(select(VerdictEvaluation))).scalars().all()
    assert len(rows) == 1
    assert rows[0].global_status == "Incompatible"


# ---------------------------------------------------------------------------
# M6-S4 — Indeterminate: no rules seeded → missing_data_log populated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m6_s4_indeterminate_no_rules(db_session):
    """
    Seed NO compatibility rules.
    verify() must return global_status="Indeterminate", risk_zones=[],
    and the persisted VerdictEvaluation must have a non-empty missing_data_log.
    """
    from sqlalchemy import select
    from app.modules.business_rules.models import VerdictEvaluation
    from app.modules.business_rules.schemas import VerificationRequest
    from app.modules.business_rules.service import CompatibilityService

    user_id = uuid.uuid4()
    morphology_id = uuid.uuid4()
    adj_id = uuid.uuid4()

    await _seed_body_shape(db_session, morphology_id)

    sid = await seed_session(db_session, user_id)
    await seed_raw_measurement(db_session, sid)
    fid = await seed_fabric(db_session, rigidity="rigid")
    model = await seed_model(db_session, cut_type="Fitted")
    await seed_model_fabric_link(db_session, model.model_id, fid)
    _make_adjustment(db_session, adj_id, sid, fid)

    # Intentionally seed NO rules

    await db_session.commit()

    request = VerificationRequest(
        adjustment_id=adj_id,
        model_id=model.model_id,
        fabric_id=fid,
        morphology_id=morphology_id,
        client_id=user_id,
    )

    patches = _m6_patches()
    for p in patches:
        p.start()
    try:
        result = await CompatibilityService.verify(request, user_id, db_session)
    finally:
        for p in patches:
            p.stop()

    assert result.global_status == "Indeterminate"
    assert result.risk_zones == []

    # Verify DB persistence — missing_data_log must be non-empty
    rows = (await db_session.execute(select(VerdictEvaluation))).scalars().all()
    assert len(rows) == 1
    assert rows[0].global_status == "Indeterminate"
    assert rows[0].missing_data_log is not None
    assert len(rows[0].missing_data_log) > 0


# ---------------------------------------------------------------------------
# M6-S5 — Fabric link absent → Reserve RiskZone added (rule_id == None)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m6_s5_fabric_link_absent_reserve(db_session):
    """
    Seed a never-fire rule; do NOT call seed_model_fabric_link.
    verify() must return global_status="Compatible_with_Reservations" and
    exactly one Reserve RiskZone with rule_id == None (fabric-link check).
    """
    from sqlalchemy import select
    from app.modules.business_rules.models import VerdictEvaluation, RiskZone
    from app.modules.business_rules.schemas import VerificationRequest
    from app.modules.business_rules.service import CompatibilityService

    user_id = uuid.uuid4()
    morphology_id = uuid.uuid4()
    adj_id = uuid.uuid4()

    await _seed_body_shape(db_session, morphology_id)

    sid = await seed_session(db_session, user_id)
    await seed_raw_measurement(db_session, sid)
    fid = await seed_fabric(db_session, rigidity="rigid")
    model = await seed_model(db_session, cut_type="Fitted")
    # Intentionally omit: await seed_model_fabric_link(db_session, model.model_id, fid)
    _make_adjustment(db_session, adj_id, sid, fid)

    # Rule that never fires (condition is never true)
    await seed_compatibility_rule(
        db_session,
        cut_type="Fitted",
        fabric_property="rigid",
        zone_name="bust",
        condition="value > 9999.0",
        severity="Reserve",
        explanation="Never-fire rule",
        admin_id=uuid.uuid4(),
    )

    await db_session.commit()

    request = VerificationRequest(
        adjustment_id=adj_id,
        model_id=model.model_id,
        fabric_id=fid,
        morphology_id=morphology_id,
        client_id=user_id,
    )

    patches = _m6_patches()
    for p in patches:
        p.start()
    try:
        result = await CompatibilityService.verify(request, user_id, db_session)
    finally:
        for p in patches:
            p.stop()

    assert result.global_status == "Compatible_with_Reservations"
    # Exactly one risk zone added by the fabric-link check
    assert len(result.risk_zones) == 1
    fabric_rz = result.risk_zones[0]
    assert fabric_rz.localized_verdict == "Reserve"
    assert fabric_rz.rule_id is None

    # Verify DB persistence
    rows = (await db_session.execute(select(VerdictEvaluation))).scalars().all()
    assert len(rows) == 1
    rz_rows = (await db_session.execute(select(RiskZone))).scalars().all()
    assert len(rz_rows) == 1
    assert rz_rows[0].rule_id is None


# ---------------------------------------------------------------------------
# M6-S6 — Morphology Avoid → Reserve RiskZone added (zone_id == None)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m6_s6_morphology_avoid_reserve(db_session):
    """
    Seed a never-fire rule, seed fabric link, seed a ModelMorphology row with
    suitability_score="Avoid".
    verify() must return global_status="Compatible_with_Reservations" and
    exactly one Reserve RiskZone with zone_id == None (morphology check).
    """
    from sqlalchemy import select
    from app.modules.business_rules.models import VerdictEvaluation, RiskZone
    from app.modules.business_rules.schemas import VerificationRequest
    from app.modules.business_rules.service import CompatibilityService

    user_id = uuid.uuid4()
    morphology_id = uuid.uuid4()
    adj_id = uuid.uuid4()

    await _seed_body_shape(db_session, morphology_id)

    sid = await seed_session(db_session, user_id)
    await seed_raw_measurement(db_session, sid)
    fid = await seed_fabric(db_session, rigidity="rigid")
    model = await seed_model(db_session, cut_type="Fitted")
    await seed_model_fabric_link(db_session, model.model_id, fid)
    _make_adjustment(db_session, adj_id, sid, fid)

    # Seed ModelMorphology with score="Avoid"
    await seed_model_morphology(
        db_session,
        model_id=model.model_id,
        morphology_id=morphology_id,
        score="Avoid",
    )

    # Rule that never fires
    await seed_compatibility_rule(
        db_session,
        cut_type="Fitted",
        fabric_property="rigid",
        zone_name="bust",
        condition="value > 9999.0",
        severity="Reserve",
        explanation="Never-fire rule",
        admin_id=uuid.uuid4(),
    )

    await db_session.commit()

    request = VerificationRequest(
        adjustment_id=adj_id,
        model_id=model.model_id,
        fabric_id=fid,
        morphology_id=morphology_id,
        client_id=user_id,
    )

    patches = _m6_patches()
    for p in patches:
        p.start()
    try:
        result = await CompatibilityService.verify(request, user_id, db_session)
    finally:
        for p in patches:
            p.stop()

    assert result.global_status == "Compatible_with_Reservations"
    # Exactly one risk zone added by the morphology check
    assert len(result.risk_zones) == 1
    morph_rz = result.risk_zones[0]
    assert morph_rz.localized_verdict == "Reserve"
    assert morph_rz.zone_id is None

    # Verify DB persistence
    rows = (await db_session.execute(select(VerdictEvaluation))).scalars().all()
    assert len(rows) == 1
    rz_rows = (await db_session.execute(select(RiskZone))).scalars().all()
    assert len(rz_rows) == 1
    assert rz_rows[0].zone_id is None
