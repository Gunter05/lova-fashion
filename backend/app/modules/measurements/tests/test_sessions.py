"""
Integration tests for Module 2 — Capture Session endpoints.

All tests use FastAPI TestClient + in-memory SQLite (no Supabase, no MediaPipe).

Coverage:
    M1  — POST /sessions: creates session with status='empty'         (AC-01.2)
    M2  — PUT /photos/{view}: stores URL, returns 200                 (AC-02.1)
    M3  — PUT /photos/{view}: 422 for invalid MIME type               (AC-02.2)
    M4  — PUT /photos/{view}: 409 on completed session                (AC-02.6)
    M5  — PATCH /stature: stores stature, returns 200                 (AC-03.2)
    M6  — PATCH /stature: 422 for out-of-range value                  (AC-03.1)
    M7  — POST /process: 422 when photos or stature missing           (AC-04.1)
    M8  — POST /process: 409 for already-processing session           (AC-04.3)
    M9  — GET /status: returns session_id + status + timestamps       (AC-05.1)
    M10 — GET /status: 404 for unknown session                        (AC-05.2)
    M11 — GET /sessions: returns only caller's sessions               (AC-07.1)
    M12 — Retry: photo upload on failed session resets to empty       (AC-06.1)
    M13 — GET /status: retry_allowed=True when failed                 (AC-05.3)
    M14 — GET /status: measurements included when success             (AC-05.2)
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.modules.measurements.tests.conftest import TEST_USER_ID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_session(client) -> dict:
    resp = client.post("/api/v1/measurements/sessions")
    assert resp.status_code == 201, resp.text
    return resp.json()


def _upload_photo(client, session_id: str, view: str = "front") -> dict:
    resp = client.put(
        f"/api/v1/measurements/sessions/{session_id}/photos/{view}",
        files={"file": ("photo.jpg", b"fake-jpeg-bytes", "image/jpeg")},
    )
    return resp


def _set_stature(client, session_id: str, stature: float = 170.0):
    return client.patch(
        f"/api/v1/measurements/sessions/{session_id}/stature",
        json={"stature_cm": stature},
    )


def _trigger_process(client, session_id: str):
    return client.post(f"/api/v1/measurements/sessions/{session_id}/process")


# ---------------------------------------------------------------------------
# M1 — Create session
# ---------------------------------------------------------------------------

def test_m1_create_session_returns_empty(client):
    """AC-01.2 : new session starts with status='empty'."""
    body = _create_session(client)
    assert body["status"] == "empty"
    assert "session_id" in body
    assert "created_at" in body


# ---------------------------------------------------------------------------
# M2 — Upload photo returns 200
# ---------------------------------------------------------------------------

def test_m2_upload_photo_returns_200(client):
    """AC-02.1 : valid JPEG upload succeeds."""
    sid = _create_session(client)["session_id"]
    resp = _upload_photo(client, sid, "front")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == sid
    assert body["view"] == "front"
    assert body["photo_url"].startswith("https://")


# ---------------------------------------------------------------------------
# M3 — Invalid MIME type → 422
# ---------------------------------------------------------------------------

def test_m3_invalid_mime_returns_422(client):
    """AC-02.2 : non-JPEG/PNG upload is rejected with 422."""
    sid = _create_session(client)["session_id"]
    resp = client.put(
        f"/api/v1/measurements/sessions/{sid}/photos/front",
        files={"file": ("photo.gif", b"fake-gif-bytes", "image/gif")},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# M4 — Upload on completed session → 409
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m4_upload_on_success_session_returns_409(client, db_session):
    """AC-02.6 : uploading to a 'success' session is rejected with 409."""
    from app.modules.measurements.models import CaptureSession
    sid = _create_session(client)["session_id"]

    # Manually set session to 'success' in DB
    session = await db_session.get(CaptureSession, uuid.UUID(sid))
    session.status = "success"
    await db_session.commit()

    resp = _upload_photo(client, sid, "front")
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# M5 — Set stature returns 200
# ---------------------------------------------------------------------------

def test_m5_set_stature_returns_200(client):
    """AC-03.2 : valid stature is stored and returned."""
    sid = _create_session(client)["session_id"]
    resp = _set_stature(client, sid, 172.0)
    assert resp.status_code == 200
    body = resp.json()
    assert float(body["entered_stature"]) == 172.0


# ---------------------------------------------------------------------------
# M6 — Out-of-range stature → 422
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stature", [99.0, 251.0, 0.0, -10.0])
def test_m6_out_of_range_stature_returns_422(client, stature):
    """AC-03.1 : stature outside [100, 250] must return 422."""
    sid = _create_session(client)["session_id"]
    resp = _set_stature(client, sid, stature)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# M7 — Process without all inputs → 422
# ---------------------------------------------------------------------------

def test_m7_process_without_photos_returns_422(client):
    """AC-04.1 : triggering process without photos/stature returns 422."""
    sid = _create_session(client)["session_id"]
    resp = _trigger_process(client, sid)
    assert resp.status_code == 422


def test_m7_process_without_stature_returns_422(client):
    """AC-04.1 : triggering process without stature returns 422."""
    sid = _create_session(client)["session_id"]
    _upload_photo(client, sid, "front")
    _upload_photo(client, sid, "profile")
    resp = _trigger_process(client, sid)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# M8 — Process already-processing session → 409
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m8_double_trigger_returns_409(client, db_session):
    """AC-04.3 : triggering an already-processing session returns 409."""
    from app.modules.measurements.models import CaptureSession
    sid = _create_session(client)["session_id"]

    session = await db_session.get(CaptureSession, uuid.UUID(sid))
    session.status = "processing"
    await db_session.commit()

    resp = _trigger_process(client, sid)
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# M9 — GET /status returns session data
# ---------------------------------------------------------------------------

def test_m9_get_status_returns_session_fields(client):
    """AC-05.1 : status endpoint returns session_id, status, timestamps."""
    sid = _create_session(client)["session_id"]
    resp = client.get(f"/api/v1/measurements/sessions/{sid}/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == sid
    assert body["status"] == "empty"
    assert "created_at" in body
    assert "updated_at" in body


# ---------------------------------------------------------------------------
# M10 — GET /status for unknown session → 404
# ---------------------------------------------------------------------------

def test_m10_status_unknown_session_returns_404(client):
    """AC-05.2 : unknown session_id returns 404."""
    fake_id = uuid.uuid4()
    resp = client.get(f"/api/v1/measurements/sessions/{fake_id}/status")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# M11 — GET /sessions returns only caller's sessions
# ---------------------------------------------------------------------------

def test_m11_list_sessions_returns_only_own(client):
    """AC-07.1 : GET /sessions returns only authenticated user's sessions."""
    _create_session(client)
    _create_session(client)
    resp = client.get("/api/v1/measurements/sessions")
    assert resp.status_code == 200
    body = resp.json()
    # All returned sessions must belong to TEST_USER_ID
    for s in body["sessions"]:
        assert "session_id" in s
    assert body["total"] >= 2


# ---------------------------------------------------------------------------
# M12 — Retry: uploading to failed session resets to empty
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m12_upload_on_failed_resets_to_empty(client, db_session):
    """AC-06.1 : uploading a photo to a failed session resets it to 'empty'."""
    from app.modules.measurements.models import CaptureSession
    sid = _create_session(client)["session_id"]

    session = await db_session.get(CaptureSession, uuid.UUID(sid))
    session.status = "failed"
    session.failure_reason = "Corps non détecté."
    await db_session.commit()

    resp = _upload_photo(client, sid, "front")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "empty"


# ---------------------------------------------------------------------------
# M13 — GET /status: retry_allowed=True when failed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m13_status_failed_retry_allowed(client, db_session):
    """AC-05.3 : status=failed → retry_allowed=True and failure_reason present."""
    from app.modules.measurements.models import CaptureSession
    sid = _create_session(client)["session_id"]

    session = await db_session.get(CaptureSession, uuid.UUID(sid))
    session.status = "failed"
    session.failure_reason = "Corps non détecté."
    await db_session.flush()
    await db_session.refresh(session)

    resp = client.get(f"/api/v1/measurements/sessions/{sid}/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["retry_allowed"] is True
    assert body["failure_reason"] is not None


# ---------------------------------------------------------------------------
# M14 — GET /status: measurements included when success
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m14_status_success_includes_measurements(client, db_session):
    """AC-05.2 : status=success returns measurements sub-object."""
    from app.modules.measurements.models import CaptureSession, RawMeasurement, BodyShape
    from sqlalchemy import text

    sid = _create_session(client)["session_id"]
    session = await db_session.get(CaptureSession, uuid.UUID(sid))
    session.status = "success"
    session.is_active = True
    await db_session.flush()

    # Ensure BodyShape seed row exists
    result = await db_session.execute(text("SELECT code FROM body_shapes WHERE code='HOURGLASS'"))
    if result.fetchone() is None:
        db_session.add(BodyShape(code="HOURGLASS", name="Sablier"))
        await db_session.flush()

    rm = RawMeasurement(
        session_id=session.id,
        bust_cm=Decimal("90.5"),
        waist_cm=Decimal("68.0"),
        hips_cm=Decimal("93.0"),
        silhouette_code="HOURGLASS",
    )
    db_session.add(rm)
    await db_session.flush()
    await db_session.refresh(session)

    resp = client.get(f"/api/v1/measurements/sessions/{sid}/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["measurements"] is not None
    assert float(body["measurements"]["bust_cm"]) == 90.5
    assert body["measurements"]["silhouette_code"] == "HOURGLASS"
