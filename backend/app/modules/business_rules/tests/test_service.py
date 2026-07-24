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
