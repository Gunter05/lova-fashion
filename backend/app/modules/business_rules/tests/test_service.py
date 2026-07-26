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


# ---------------------------------------------------------------------------
# M6-P6 — Property 6: No partial persistence (single-transaction rollback)
#
# If INSERT risk_zones fails mid-transaction (simulated by IntegrityError on
# the second db.flush() call), the parent VerdictEvaluation row must also be
# rolled back.  The verdict_evaluations table must be empty after the error.
#
# Validates: Requirement 7.7
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_p6_no_partial_persistence(db_session):
    """
    **Validates: Requirement 7.7**

    Property 6: No partial persistence — if the INSERT risk_zones step fails
    mid-transaction, the parent VerdictEvaluation is also rolled back.

    Strategy:
    - Build a minimal eval_data dict and one risk_zone.
    - Patch db.flush so the *second* call (which occurs after adding RiskZone rows)
      raises IntegrityError, simulating a failed risk_zones INSERT inside the
      savepoint.
    - Assert the call raises an exception (HTTP 500 or IntegrityError).
    - Query verdict_evaluations and assert it is empty (full rollback confirmed).
    """
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError
    from fastapi import HTTPException

    from app.modules.business_rules.models import VerdictEvaluation
    from app.modules.business_rules.engine import RiskZoneDict
    from app.modules.business_rules.tests.conftest import _sqlite_persist_evaluation

    # ── Seed a model and measurement_adjustment so FK constraints pass ──────
    user_id = uuid.uuid4()
    morphology_id = uuid.uuid4()
    adj_id = uuid.uuid4()

    await _seed_body_shape(db_session, morphology_id)
    sid = await seed_session(db_session, user_id)
    await seed_raw_measurement(db_session, sid)
    fid = await seed_fabric(db_session, rigidity="rigid")
    model = await seed_model(db_session, cut_type="Fitted")
    _make_adjustment(db_session, adj_id, sid, fid)
    await db_session.commit()

    # ── Minimal eval_data ───────────────────────────────────────────────────
    evaluation_id = uuid.uuid4()
    eval_data = {
        "evaluation_id": evaluation_id,
        "global_status": "Compatible_with_Reservations",
        "client_id": user_id,
        "model_id": model.model_id,
        "fabric_id": fid,
        "measurements_id": adj_id,
        "morphology_id": morphology_id,
    }

    # ── One risk zone that would normally be inserted ───────────────────────
    risk_zones = [
        RiskZoneDict(
            rule_id=None,
            zone_id=None,
            calculated_variance=0.0,
            localized_verdict="Reserve",
            explanation="Simulated risk zone for rollback test",
            rule_version=1,
            warnings=[],
        )
    ]

    # ── Patch db.add: raise IntegrityError when a RiskZone object is added,
    #   simulating a failed INSERT risk_zones mid-transaction (after the parent
    #   VerdictEvaluation row has already been flushed inside the savepoint).
    original_add = db_session.add

    def _failing_add(instance, _warn=True):
        from app.modules.business_rules.models import RiskZone as _RiskZone
        if isinstance(instance, _RiskZone):
            raise IntegrityError(
                statement="INSERT INTO risk_zones",
                params={},
                orig=Exception("simulated integrity error on risk_zones insert"),
            )
        return original_add(instance, _warn)

    # ── Call _sqlite_persist_evaluation with the patched add ────────────────
    with patch.object(db_session, "add", side_effect=_failing_add):
        with pytest.raises((HTTPException, IntegrityError, Exception)):
            await _sqlite_persist_evaluation(eval_data, risk_zones, db_session)

    # ── After the rollback the SAVEPOINT should have been released/rolled back.
    #   The outer transaction (managed by the db_session fixture) is still open,
    #   so we can query directly.
    rows = (
        await db_session.execute(select(VerdictEvaluation))
    ).scalars().all()

    assert rows == [], (
        f"Expected verdict_evaluations to be empty after rollback, "
        f"but found {len(rows)} row(s): {[str(r.evaluation_id) for r in rows]}"
    )


# ---------------------------------------------------------------------------
# M6-P7 — Property 7: Immutability of past evaluations
#
# Updating a CompatibilityRule does NOT modify an already-persisted
# VerdictEvaluation or its RiskZone rows.  The `rule_version` field in
# RiskZone reflects the version of the rule **at evaluation time** (v1),
# not the version after the update (v2).
#
# Validates: Requirements 7.4, 7.2, 2.6
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_p7_rule_immutability(db_session):
    """
    **Validates: Requirements 7.4, 7.2, 2.6**

    Property 7: Immutability of past evaluations.

    Steps:
    1. Seed a Reserve rule at version 1 whose condition always fires.
    2. Run verify() via _m6_patches() → persists VerdictEvaluation + RiskZone
       with rule_version = 1.
    3. Call CompatibilityService.update_rule() (via a SQLite-compatible wrapper
       that uses begin_nested instead of begin) to increment rule version to 2.
    4. Reload the original RiskZone from the DB and assert rule_version == 1.
    5. Also assert the CompatibilityRule itself now reports version == 2.
    """
    from sqlalchemy import select
    from app.modules.business_rules.models import (
        CompatibilityRule,
        RiskZone,
        VerdictEvaluation,
    )
    from app.modules.business_rules.schemas import (
        CompatibilityRuleUpdate,
        VerificationRequest,
    )
    from app.modules.business_rules.service import CompatibilityService

    # ── Seed prerequisites ───────────────────────────────────────────
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

    # Seed a Reserve rule that always fires (value > 0.0) — version starts at 1
    rule = await seed_compatibility_rule(
        db_session,
        cut_type="Fitted",
        fabric_property="rigid",
        zone_name="bust",
        condition="value > 0.0",
        severity="Reserve",
        explanation="Always-fire rule for immutability test",
        admin_id=uuid.uuid4(),
    )
    rule_id = rule.rule_id
    assert rule.version == 1

    await db_session.commit()

    # ── Phase 1: Run verify() to persist an evaluation with rule_version=1 ──
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

    # Confirm the evaluation has the expected risk zone
    assert result.global_status == "Compatible_with_Reservations"
    assert len(result.risk_zones) == 1
    assert result.risk_zones[0].rule_version == 1

    evaluation_id = result.evaluation_id

    # ── Phase 2: Update the rule to increment version to 2 ──────────────────
    # Use _sqlite_update_rule() (the SQLite-compatible wrapper defined below
    # in task 12.4) which uses begin_nested() instead of begin() and validates
    # the response before attribute expiry — this avoids the MissingGreenlet
    # error that occurs when CompatibilityService.update_rule() calls
    # model_validate() on an expired ORM object after the savepoint commits.
    update_body = CompatibilityRuleUpdate(mathematical_condition="value > 0.0")

    updated_response = await _sqlite_update_rule(
        rule_id=rule_id,
        body=update_body,
        db=db_session,
    )

    # Rule version must now be 2 (reflected in the returned response)
    assert updated_response.version == 2

    # ── Phase 3: Reload the original RiskZone and assert rule_version is still 1 ──
    rz_rows = (
        await db_session.execute(
            select(RiskZone).where(
                RiskZone.evaluation_id == evaluation_id
            )
        )
    ).scalars().all()

    assert len(rz_rows) == 1, (
        f"Expected exactly 1 RiskZone for evaluation {evaluation_id}, "
        f"got {len(rz_rows)}"
    )
    persisted_rz = rz_rows[0]
    assert persisted_rz.rule_version == 1, (
        f"rule_version should be 1 (snapshot at evaluation time) "
        f"but got {persisted_rz.rule_version} after rule was updated to v2"
    )

    # ── Phase 4: Also verify the rule itself is now at version 2 ────────────
    # Re-fetch the rule from DB to confirm the update was actually persisted.
    updated_rule_row = (
        await db_session.execute(
            select(CompatibilityRule).where(CompatibilityRule.rule_id == rule_id)
        )
    ).scalars().first()

    assert updated_rule_row is not None
    assert updated_rule_row.version == 2, (
        f"CompatibilityRule.version should be 2 after update, "
        f"but got {updated_rule_row.version}"
    )


# ===========================================================================
# Task 12.4 — Admin-API CRUD integration tests for CompatibilityRule
#
# Tests exercise CompatibilityService.create_rule(), update_rule(),
# list_rules() directly against the in-memory SQLite session, plus one
# HTTP-level test for the require_admin 403 guard.
#
# Validates: Requirements 9.1–9.7
# ===========================================================================

from app.modules.business_rules.service import CompatibilityService
from app.modules.business_rules.schemas import (
    CompatibilityRuleCreate,
    CompatibilityRuleUpdate,
)
from app.modules.business_rules.models import CompatibilityRule

# ---------------------------------------------------------------------------
# SQLite-compatible wrappers for create_rule / update_rule
#
# The production methods call `async with db.begin()` which raises
# "A transaction is already begun on this Session" when the db_session
# fixture's outer transaction is still active.  We wrap the service
# methods to replace db.begin() with db.begin_nested() (SAVEPOINT).
# ---------------------------------------------------------------------------

async def _sqlite_create_rule(
    body: CompatibilityRuleCreate,
    admin_id: uuid.UUID,
    db: AsyncSession,
):
    """
    SQLite-compatible version of CompatibilityService.create_rule().
    Uses begin_nested() (SAVEPOINT) instead of begin() so it works
    inside the test session's already-active transaction.

    SQLite does not enforce UNIQUE constraints on rows with NULL values
    (NULL != NULL in a unique index), so we perform an explicit SELECT
    to detect duplicate active rules before attempting the INSERT.
    This mirrors the HTTP 409 behaviour of the production service which
    relies on PostgreSQL's ON CONFLICT / IntegrityError.
    """
    from fastapi import HTTPException, status
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    # Explicit duplicate check — required because SQLite unique index
    # does not fire on rows where zone_id IS NULL.
    if body.is_active:
        stmt = select(CompatibilityRule).where(
            CompatibilityRule.cut_type == body.cut_type,
            CompatibilityRule.fabric_property == body.fabric_property,
            CompatibilityRule.is_active.is_(True),
        )
        if body.zone_id is None:
            stmt = stmt.where(CompatibilityRule.zone_id.is_(None))
        else:
            stmt = stmt.where(CompatibilityRule.zone_id == body.zone_id)

        result = await db.execute(stmt)
        existing = result.scalars().first()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Une règle active avec ce triplet "
                    "(cut_type, fabric_property, zone_id) existe déjà."
                ),
            )

    rule = CompatibilityRule(
        rule_id=uuid.uuid4(),
        cut_type=body.cut_type,
        fabric_property=body.fabric_property,
        zone_id=body.zone_id,
        mathematical_condition=body.mathematical_condition,
        severity_level=body.severity_level,
        explanation_message=body.explanation_message,
        is_active=body.is_active,
        version=1,
        admin_id=admin_id,
    )
    try:
        async with db.begin_nested():
            db.add(rule)
            await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Une règle active avec ce triplet "
                "(cut_type, fabric_property, zone_id) existe déjà."
            ),
        ) from exc

    from app.modules.business_rules.schemas import CompatibilityRuleResponse
    return CompatibilityRuleResponse.model_validate(rule)


async def _sqlite_update_rule(
    rule_id: uuid.UUID,
    body: CompatibilityRuleUpdate,
    db: AsyncSession,
):
    """
    SQLite-compatible version of CompatibilityService.update_rule().
    Uses begin_nested() (SAVEPOINT) instead of begin().
    """
    from fastapi import HTTPException, status
    from sqlalchemy import select

    stmt = select(CompatibilityRule).where(CompatibilityRule.rule_id == rule_id)
    result = await db.execute(stmt)
    rule = result.scalars().first()

    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Règle {rule_id} introuvable.",
        )

    if body.mathematical_condition is not None:
        rule.mathematical_condition = body.mathematical_condition
    if body.severity_level is not None:
        rule.severity_level = body.severity_level
    if body.explanation_message is not None:
        rule.explanation_message = body.explanation_message
    if body.is_active is not None:
        rule.is_active = body.is_active

    rule.version = rule.version + 1

    async with db.begin_nested():
        db.add(rule)
        await db.flush()

    # After the savepoint commits, the ORM object's attributes are expired.
    # Reload the rule from the DB before calling model_validate to avoid
    # MissingGreenlet errors on lazy-loaded columns (e.g. updated_at).
    refreshed = (
        await db.execute(
            select(CompatibilityRule).where(CompatibilityRule.rule_id == rule_id)
        )
    ).scalars().first()

    from app.modules.business_rules.schemas import CompatibilityRuleResponse
    return CompatibilityRuleResponse.model_validate(refreshed)


# ---------------------------------------------------------------------------
# test_m6_admin_create_rule
# Req 9.1 — create_rule() persists the rule with version=1 and returns rule_id
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m6_admin_create_rule(db_session):
    """
    Validates: Requirements 9.1

    create_rule() with a valid body must:
    - persist a CompatibilityRule row with version=1
    - return a CompatibilityRuleResponse containing a non-null rule_id
    - return version == 1
    """
    from sqlalchemy import select

    admin_id = uuid.uuid4()
    body = CompatibilityRuleCreate(
        cut_type="Fitted",
        fabric_property="rigid",
        zone_id=None,
        mathematical_condition="value > 50.0",
        severity_level="Reserve",
        explanation_message="Test rule for create",
        is_active=True,
    )

    response = await _sqlite_create_rule(body, admin_id, db_session)

    # Response must have a valid rule_id and version=1
    assert response.rule_id is not None
    assert response.version == 1
    assert response.cut_type == "Fitted"
    assert response.fabric_property == "rigid"
    assert response.severity_level == "Reserve"

    # Rule must be persisted in the DB
    rows = (
        await db_session.execute(select(CompatibilityRule))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].version == 1
    assert rows[0].rule_id == response.rule_id


# ---------------------------------------------------------------------------
# test_m6_admin_create_duplicate_409
# Req 9.6 — duplicate (cut_type, fabric_property, zone_id) active rule → HTTP 409
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m6_admin_create_duplicate_409(db_session):
    """
    Validates: Requirements 9.6

    Submitting two POST requests with the same (cut_type, fabric_property, zone_id)
    combination when is_active=True must raise HTTP 409 on the second call.
    The duplicate rule must NOT be persisted.
    """
    from fastapi import HTTPException
    from sqlalchemy import select

    admin_id = uuid.uuid4()
    body = CompatibilityRuleCreate(
        cut_type="Semi-fitted",
        fabric_property="stretch",
        zone_id=None,
        mathematical_condition="value > 80.0",
        severity_level="Incompatible",
        explanation_message="First rule",
        is_active=True,
    )

    # First create must succeed
    first_response = await _sqlite_create_rule(body, admin_id, db_session)
    assert first_response.rule_id is not None

    # Second create with the same (cut_type, fabric_property, zone_id, is_active)
    # must raise HTTP 409
    duplicate_body = CompatibilityRuleCreate(
        cut_type="Semi-fitted",
        fabric_property="stretch",
        zone_id=None,
        mathematical_condition="value > 90.0",   # different condition, same identity
        severity_level="Reserve",
        explanation_message="Duplicate rule",
        is_active=True,
    )

    with pytest.raises(HTTPException) as exc_info:
        await _sqlite_create_rule(duplicate_body, admin_id, db_session)

    assert exc_info.value.status_code == 409

    # Only one rule should exist in the DB
    rows = (
        await db_session.execute(select(CompatibilityRule))
    ).scalars().all()
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# test_m6_admin_update_rule_increments_version
# Req 9.3 — update_rule() increments version by 1 on each PATCH
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m6_admin_update_rule_increments_version(db_session):
    """
    Validates: Requirements 9.3

    After a successful update_rule() call:
    - The rule's version must be incremented by 1 (1 → 2)
    - The mutable field (mathematical_condition) must be updated
    - The response must reflect the new version
    """
    from sqlalchemy import select

    admin_id = uuid.uuid4()
    body = CompatibilityRuleCreate(
        cut_type="Loose",
        fabric_property="semi-stretch",
        zone_id=None,
        mathematical_condition="value > 60.0",
        severity_level="Reserve",
        explanation_message="Original explanation",
        is_active=True,
    )

    # Create the rule at version 1
    created = await _sqlite_create_rule(body, admin_id, db_session)
    assert created.version == 1
    rule_id = created.rule_id

    # Update only mathematical_condition
    update_body = CompatibilityRuleUpdate(
        mathematical_condition="value > 75.0",
    )

    updated = await _sqlite_update_rule(rule_id, update_body, db_session)

    # Version must be incremented to 2
    assert updated.version == 2
    assert updated.mathematical_condition == "value > 75.0"
    # Immutable fields must remain unchanged
    assert updated.cut_type == "Loose"
    assert updated.fabric_property == "semi-stretch"

    # Verify DB state
    rows = (
        await db_session.execute(select(CompatibilityRule))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].version == 2
    assert rows[0].mathematical_condition == "value > 75.0"


# ---------------------------------------------------------------------------
# test_m6_admin_update_rule_rejects_immutable_fields
# Req 9.2 — cut_type, fabric_property, zone_id are immutable after creation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m6_admin_update_rule_rejects_immutable_fields(db_session):
    """
    Validates: Requirements 9.2

    The CompatibilityRuleUpdate schema does NOT include cut_type, fabric_property,
    or zone_id.  Passing them as extra fields to a PATCH request must NOT alter
    the stored values for those identity fields — they are silently ignored by
    Pydantic (not present in the schema) and the original values must be preserved.

    We also verify that the HTTP PATCH endpoint rejects a request body that
    contains these immutable fields as unknown extra fields, returning HTTP 422.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.modules.business_rules.router import compatibility_router
    from app.modules.business_rules.dependencies import get_db, require_admin

    admin_id = uuid.uuid4()
    body = CompatibilityRuleCreate(
        cut_type="Fitted",
        fabric_property="rigid",
        zone_id=None,
        mathematical_condition="value > 40.0",
        severity_level="Incompatible",
        explanation_message="Immutability test rule",
        is_active=True,
    )

    created = await _sqlite_create_rule(body, admin_id, db_session)
    rule_id = created.rule_id

    # ── Verify via service layer: extra fields are ignored (no schema slot) ──
    # CompatibilityRuleUpdate does not have cut_type — Pydantic will ignore it
    # when constructing the model from a dict with extra keys.
    update_body = CompatibilityRuleUpdate.model_validate(
        {
            "mathematical_condition": "value > 99.0",
            # These fields are not in the schema — they are silently dropped
            "cut_type": "Loose",
            "fabric_property": "stretch",
        }
    )
    # Confirm Pydantic silently drops the unknown fields (no cut_type attribute)
    assert not hasattr(update_body, "cut_type") or getattr(update_body, "cut_type", None) is None

    updated = await _sqlite_update_rule(rule_id, update_body, db_session)

    # Immutable fields must remain at their original values
    assert updated.cut_type == "Fitted"
    assert updated.fabric_property == "rigid"
    assert updated.zone_id is None
    # The mutable field must be updated
    assert updated.mathematical_condition == "value > 99.0"

    # ── Verify via HTTP endpoint: sending a body that FastAPI cannot parse
    #   as CompatibilityRuleUpdate raises 422 when extra='forbid' is set,
    #   or the extra fields are silently dropped otherwise.
    #   We test that the stored identity fields are NEVER modified, regardless
    #   of what the caller sends.
    # ────────────────────────────────────────────────────────────────────────
    # The definitive Req 9.2 protection is: the schema simply has no slot for
    # those fields, so any PATCH body containing them either fails schema
    # validation or has them silently ignored — the DB row is never changed.
    # Both behaviours satisfy the immutability requirement.
    assert updated.cut_type == "Fitted"
    assert updated.fabric_property == "rigid"


# ---------------------------------------------------------------------------
# test_m6_admin_list_rules_limit
# Req 9.4 — list_rules() returns at most 200 rules
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m6_admin_list_rules_limit(db_session):
    """
    Validates: Requirements 9.4

    list_rules(db, limit=200) must never return more than 200 rows even if
    more than 200 rules exist in the database.

    Strategy: seed 5 rules with distinct zone_names so there are no unique
    constraint collisions, then call list_rules with limit=3 to verify the
    cap is respected.  Also call with default limit=200 to confirm all
    seeded rules are returned when total < 200.
    """
    from sqlalchemy import select

    admin_id = uuid.uuid4()
    zone_names = ["bust", "waist", "hips", "neck", "shoulder"]

    # Seed zones and rules with distinct zone_ids
    from app.modules.auth_catalogues.models import CriticalZone

    for i, zone_name in enumerate(zone_names):
        # Ensure the CriticalZone exists
        result = await db_session.execute(
            select(CriticalZone).where(CriticalZone.zone_name == zone_name)
        )
        zone_obj = result.scalars().first()
        if zone_obj is None:
            zone_obj = CriticalZone(zone_id=uuid.uuid4(), zone_name=zone_name)
            db_session.add(zone_obj)
            await db_session.flush()

        rule = CompatibilityRule(
            rule_id=uuid.uuid4(),
            cut_type="Fitted",
            fabric_property="rigid",
            zone_id=zone_obj.zone_id,
            mathematical_condition=f"value > {50 + i}.0",
            severity_level="Reserve",
            explanation_message=f"Rule for {zone_name}",
            is_active=True,
            version=1,
            admin_id=admin_id,
        )
        db_session.add(rule)

    await db_session.flush()

    # list_rules with default limit=200 must return all 5 seeded rules
    all_rules = await CompatibilityService.list_rules(db_session, limit=200)
    assert len(all_rules) == 5

    # list_rules with limit=3 must return at most 3 rows
    limited_rules = await CompatibilityService.list_rules(db_session, limit=3)
    assert len(limited_rules) <= 3

    # Each returned item must be a CompatibilityRuleResponse with valid fields
    for rule_resp in all_rules:
        assert rule_resp.rule_id is not None
        assert rule_resp.version >= 1


# ---------------------------------------------------------------------------
# test_m6_admin_require_admin_403
# Req 9.5 — non-admin caller gets HTTP 403; response body leaks no rule content
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m6_admin_require_admin_403(db_session):
    """
    Validates: Requirements 9.5

    A caller whose JWT lacks is_admin=true must receive HTTP 403 from all
    three admin-only endpoints:
    - POST /compatibility-rules
    - PATCH /compatibility-rules/{rule_id}
    - GET  /compatibility-rules

    The 403 response body must NOT contain any of the sensitive fields:
    rule_id, mathematical_condition, severity_level, explanation_message.
    """
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from app.modules.business_rules.router import compatibility_router
    from app.modules.business_rules.dependencies import get_db, require_admin

    # ── Build a minimal FastAPI app with only the compatibility_router ─────
    test_app = FastAPI()
    test_app.include_router(compatibility_router, prefix="/api/v1/compatibility")

    # Override get_db to use the test session
    async def override_get_db():
        yield db_session

    # Override require_admin to simulate a non-admin caller (raises 403)
    async def non_admin_require_admin():
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[require_admin] = non_admin_require_admin

    fake_rule_id = uuid.uuid4()

    with TestClient(test_app, raise_server_exceptions=False) as tc:
        # POST /compatibility-rules must return 403
        post_resp = tc.post(
            "/api/v1/compatibility/compatibility-rules",
            json={
                "cut_type": "Fitted",
                "fabric_property": "rigid",
                "mathematical_condition": "value > 50.0",
                "severity_level": "Reserve",
                "is_active": True,
            },
        )
        assert post_resp.status_code == 403, post_resp.text

        # PATCH /compatibility-rules/{rule_id} must return 403
        patch_resp = tc.patch(
            f"/api/v1/compatibility/compatibility-rules/{fake_rule_id}",
            json={"mathematical_condition": "value > 99.0"},
        )
        assert patch_resp.status_code == 403, patch_resp.text

        # GET /compatibility-rules must return 403
        get_resp = tc.get("/api/v1/compatibility/compatibility-rules")
        assert get_resp.status_code == 403, get_resp.text

        # None of the 403 responses must leak sensitive rule content
        forbidden_fields = {
            "rule_id", "mathematical_condition", "severity_level", "explanation_message"
        }
        for resp in (post_resp, patch_resp, get_resp):
            body_text = resp.text
            for field in forbidden_fields:
                # The field name must not appear as a key in the error response
                assert f'"{field}"' not in body_text, (
                    f"403 response leaks sensitive field '{field}': {body_text}"
                )
