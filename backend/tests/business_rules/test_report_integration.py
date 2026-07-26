"""
Integration tests for Module 7 — Final Result & Report (Synthesis).

Uses an in-memory SQLite DB + FastAPI TestClient (same pattern as Module 1 tests).
Covers Tasks 28–33 and Task 37 (ordering invariant).

Tasks 28–30: HTTP endpoint tests (GET /reports/…)
Task 31:    Event handler happy path
Task 32:    Event handler error paths
Task 33:    Immutability (two events → two distinct rows)
Task 37:    Hypothesis — report list ordering invariant

Req 5 AC1–5 · Req 6 AC1–2 · Req 7 AC1–5 · Req 8 AC2 · Req 9 AC1–2
Design §Correctness Property 6
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.modules.business_rules.report_handler import make_compatibility_evaluated_handler
from app.modules.business_rules.report_router import router as report_router
from app.modules.business_rules.report_service import ReportService

# Build a minimal FastAPI app with only the report router mounted
# This avoids the cross-module import chain that other modules add to app.main
app = FastAPI()
app.include_router(report_router, prefix="/api/v1")

# ── SQLite in-memory helpers ──────────────────────────────────────────────────

SQLITE_URL = "sqlite+aiosqlite:///:memory:"

# Fixed IDs used across tests
_CLIENT_CNI   = "TST777001"
_CLIENT2_CNI  = "TST777002"
_TAILOR_CNI   = "TST777003"
_FABRIC_ID    = str(uuid.uuid4())
_MODEL_ID     = str(uuid.uuid4())
_ADJ_ID       = str(uuid.uuid4())
_ADJ_BUST     = 90.0
_ADJ_WAIST    = 70.0
_ADJ_HIPS     = 95.0


def _make_engine_and_session():
    engine = create_async_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    sm = async_sessionmaker(
        engine, class_=AsyncSession,
        expire_on_commit=False, autoflush=False, autocommit=False,
    )
    return engine, sm


async def _create_schema(engine) -> None:
    async with engine.begin() as conn:
        # Minimal schema — no CHECK constraints for SQLite compatibility
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
            CREATE TABLE IF NOT EXISTS token_denylist (
                jti        TEXT     NOT NULL PRIMARY KEY,
                expires_at DATETIME NOT NULL
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS capture_sessions (
                id       VARCHAR(36) NOT NULL PRIMARY KEY,
                user_id  VARCHAR(36) NOT NULL,
                status   VARCHAR(30) NOT NULL DEFAULT 'success',
                is_active BOOLEAN    NOT NULL DEFAULT 1
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS measurement_adjustments (
                id                UUID         NOT NULL PRIMARY KEY,
                session_id        VARCHAR(36)  NOT NULL,
                fabric_id         VARCHAR(36)  NOT NULL,
                raw_bust_cm       NUMERIC(5,1) NOT NULL,
                raw_waist_cm      NUMERIC(5,1) NOT NULL,
                raw_hips_cm       NUMERIC(5,1) NOT NULL,
                bust_ease_cm      NUMERIC(4,1) NOT NULL,
                waist_ease_cm     NUMERIC(4,1) NOT NULL,
                hips_ease_cm      NUMERIC(4,1) NOT NULL,
                adjusted_bust_cm  NUMERIC(5,1) NOT NULL,
                adjusted_waist_cm NUMERIC(5,1) NOT NULL,
                adjusted_hips_cm  NUMERIC(5,1) NOT NULL,
                ease_source       VARCHAR(30)  NOT NULL DEFAULT 'rule',
                calculated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fabrics (
                fabric_id   VARCHAR(36) NOT NULL PRIMARY KEY,
                fabric_name VARCHAR(100) NOT NULL
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS models (
                model_id    VARCHAR(36) NOT NULL PRIMARY KEY,
                model_name  VARCHAR(100) NOT NULL
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS rapport_mesure (
                id_report             VARCHAR(36)  NOT NULL PRIMARY KEY,
                cni                   VARCHAR(9)   NOT NULL,
                adjustment_id         VARCHAR(36)  NOT NULL,
                fabric_id             VARCHAR(36)  NOT NULL,
                model_id              VARCHAR(36)  NOT NULL,
                verdict               VARCHAR(30)  NOT NULL,
                adjusted_measurements TEXT         NOT NULL,
                advice                TEXT         NOT NULL,
                incompatible_zones    TEXT         NULL,
                generated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Seed upstream entities
        await conn.execute(text("""
            INSERT OR IGNORE INTO users (cni, nom, email, mot_de_passe, role)
            VALUES
                (:c1, 'Client 1', 'c1@example.com', 'h', 'Client'),
                (:c2, 'Client 2', 'c2@example.com', 'h', 'Client'),
                (:t1, 'Tailor 1', 'tailor@example.com', 'h', 'Tailor')
        """), {"c1": _CLIENT_CNI, "c2": _CLIENT2_CNI, "t1": _TAILOR_CNI})

        await conn.execute(text(
            "INSERT OR IGNORE INTO fabrics (fabric_id, fabric_name) VALUES (:fid, 'Wax')"
        ), {"fid": _FABRIC_ID})

        await conn.execute(text(
            "INSERT OR IGNORE INTO models (model_id, model_name) VALUES (:mid, 'Robe ajustée')"
        ), {"mid": _MODEL_ID})

        sess_id = str(uuid.uuid4())
        await conn.execute(text("""
            INSERT OR IGNORE INTO capture_sessions (id, user_id, status)
            VALUES (:sid, :uid, 'success')
        """), {"sid": sess_id, "uid": _CLIENT_CNI})

        await conn.execute(text("""
            INSERT OR IGNORE INTO measurement_adjustments
                (id, session_id, fabric_id,
                 raw_bust_cm, raw_waist_cm, raw_hips_cm,
                 bust_ease_cm, waist_ease_cm, hips_ease_cm,
                 adjusted_bust_cm, adjusted_waist_cm, adjusted_hips_cm,
                 ease_source)
            VALUES
                (:aid, :sid, :fid,
                 86.0, 66.0, 91.0,
                 4.0,  4.0,  4.0,
                 :bust, :waist, :hips,
                 'rule')
        """), {
            "aid": _ADJ_ID, "sid": sess_id, "fid": _FABRIC_ID,
            "bust": _ADJ_BUST, "waist": _ADJ_WAIST, "hips": _ADJ_HIPS,
        })


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ── Module-level shared DB fixture ───────────────────────────────────────────

_ENGINE = None
_SM = None


@pytest.fixture(scope="module", autouse=True)
def report_db():
    global _ENGINE, _SM
    _ENGINE, _SM = _make_engine_and_session()
    _run(_create_schema(_ENGINE))

    async def override():
        async with _SM() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise
            finally:
                await s.close()

    app.dependency_overrides[get_db] = override
    yield
    app.dependency_overrides.clear()
    _run(_ENGINE.dispose())


# ── Helpers ───────────────────────────────────────────────────────────────────

def _valid_event(
    cni=None, adj_id=None, fabric_id=None, model_id=None, verdict="compatible"
) -> dict:
    return {
        "type": "compatibility.evaluated",
        "emitted_at": datetime.now(timezone.utc).isoformat(),
        "cni":           cni or _CLIENT_CNI,
        "adjustment_id": adj_id or _ADJ_ID,
        "fabric_id":     fabric_id or _FABRIC_ID,
        "model_id":      model_id or _MODEL_ID,
        "verdict":       verdict,
        "advice":        "Test advice.",
    }


def _headers(cni: str, role: str) -> dict:
    return {"x-user-cni": cni, "x-user-role": role}


async def _insert_report(
    cni=_CLIENT_CNI,
    adj_id=None,
    verdict="compatible",
    generated_at: datetime | None = None,
) -> str:
    import json
    report_id = str(uuid.uuid4())
    snapshot = json.dumps({
        "adjusted_bust_cm": _ADJ_BUST, "adjusted_waist_cm": _ADJ_WAIST,
        "adjusted_hips_cm": _ADJ_HIPS, "bust_ease_cm": 4.0,
        "waist_ease_cm": 4.0, "hips_ease_cm": 4.0, "ease_source": "rule",
    })
    ts = (generated_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S")
    async with _SM() as s:
        await s.execute(text("""
            INSERT INTO rapport_mesure
                (id_report, cni, adjustment_id, fabric_id, model_id,
                 verdict, adjusted_measurements, advice, generated_at)
            VALUES (:rid, :cni, :aid, :fid, :mid, :v, :snap, 'Advice', :ts)
        """), {
            "rid": report_id, "cni": cni, "aid": adj_id or _ADJ_ID,
            "fid": _FABRIC_ID, "mid": _MODEL_ID,
            "v": verdict, "snap": snapshot, "ts": ts,
        })
        await s.commit()
    return report_id


# ─────────────────────────────────────────────────────────────────────────────
# Task 28: GET /reports/{report_id}
# ─────────────────────────────────────────────────────────────────────────────

def test_get_report_client_owner_returns_200():
    """Client retrieves own report → HTTP 200 with display_hints. Req 5 AC1"""
    report_id = _run(_insert_report(_CLIENT_CNI))
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get(f"/api/v1/reports/{report_id}", headers=_headers(_CLIENT_CNI, "Client"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "display_hints" in body
    assert body["display_hints"]["verdict_color"] == "green"
    assert body["report_id"] == report_id


def test_get_report_client_other_returns_403():
    """Client retrieves another client's report → HTTP 403. Req 5 AC3"""
    report_id = _run(_insert_report(_CLIENT_CNI))
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get(f"/api/v1/reports/{report_id}", headers=_headers(_CLIENT2_CNI, "Client"))
    assert r.status_code == 403, r.text


def test_get_report_tailor_any_returns_200():
    """Tailor retrieves any report → HTTP 200. Req 5 AC4"""
    report_id = _run(_insert_report(_CLIENT_CNI))
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get(f"/api/v1/reports/{report_id}", headers=_headers(_TAILOR_CNI, "Tailor"))
    assert r.status_code == 200, r.text


def test_get_report_not_found_returns_404():
    """Non-existent report_id → HTTP 404. Req 5 AC2"""
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get(f"/api/v1/reports/{uuid.uuid4()}", headers=_headers(_CLIENT_CNI, "Client"))
    assert r.status_code == 404, r.text


def test_get_report_no_jwt_returns_401():
    """No authentication headers → HTTP 401. Req 5 AC5"""
    report_id = _run(_insert_report(_CLIENT_CNI))
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get(f"/api/v1/reports/{report_id}")
    assert r.status_code == 401, r.text


# ─────────────────────────────────────────────────────────────────────────────
# Task 29: GET /reports/me
# ─────────────────────────────────────────────────────────────────────────────

def test_list_my_reports_returns_all_ordered():
    """Client with 3 reports → HTTP 200, list of 3. Req 6 AC1"""
    unique_cni = "LST888001"
    _run(_create_extra_user(unique_cni))
    for _ in range(3):
        _run(_insert_report(unique_cni))
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/v1/reports/me", headers=_headers(unique_cni, "Client"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 3
    assert len(body["reports"]) == 3


def test_list_my_reports_empty_returns_200():
    """Client with no reports → HTTP 200, empty list. Req 6 AC2"""
    unique_cni = "LST888002"
    _run(_create_extra_user(unique_cni))
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/v1/reports/me", headers=_headers(unique_cni, "Client"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 0
    assert body["reports"] == []


def test_list_my_reports_tailor_returns_403():
    """Tailor calling /reports/me → HTTP 403. Req 6 AC4"""
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/v1/reports/me", headers=_headers(_TAILOR_CNI, "Tailor"))
    assert r.status_code == 403, r.text


# ─────────────────────────────────────────────────────────────────────────────
# Task 30: GET /reports/client/{cni}
# ─────────────────────────────────────────────────────────────────────────────

def test_tailor_list_client_reports_returns_200():
    """Tailor retrieves client's reports → HTTP 200. Req 7 AC1"""
    _run(_insert_report(_CLIENT_CNI))
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get(f"/api/v1/reports/client/{_CLIENT_CNI}",
                  headers=_headers(_TAILOR_CNI, "Tailor"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 1


def test_tailor_list_client_no_reports_returns_200():
    """Tailor retrieves existing client with no reports → HTTP 200, total=0. Req 7 AC2"""
    unique_cni = "LST888003"
    _run(_create_extra_user(unique_cni))
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get(f"/api/v1/reports/client/{unique_cni}",
                  headers=_headers(_TAILOR_CNI, "Tailor"))
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 0


def test_client_list_other_client_returns_403():
    """Client calling /reports/client/{cni} → HTTP 403. Req 7 AC3"""
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get(f"/api/v1/reports/client/{_CLIENT_CNI}",
                  headers=_headers(_CLIENT2_CNI, "Client"))
    assert r.status_code == 403, r.text


def test_tailor_unknown_cni_returns_404():
    """Tailor queries non-existent CNI → HTTP 404. Req 7 AC4"""
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/v1/reports/client/ZZZ999999",
                  headers=_headers(_TAILOR_CNI, "Tailor"))
    assert r.status_code == 404, r.text


# ─────────────────────────────────────────────────────────────────────────────
# Task 31: Event handler happy path
# ─────────────────────────────────────────────────────────────────────────────

def test_event_handler_happy_path_creates_report():
    """
    Emit valid compatible event → one rapport_mesure row, correct fields.
    Req 1 AC1 · Req 9 AC1–2
    """
    published_events: list[dict] = []

    async def run():
        from app.modules.auth_user_profile.events.bus import EventBus
        mock_bus = EventBus()
        mock_bus.subscribe("report.saved", lambda p: published_events.append(p) or asyncio.sleep(0))

        # Patch the bus used by the handler
        import app.modules.auth_user_profile.events.bus as bus_module
        original_bus = bus_module.event_bus
        bus_module.event_bus = mock_bus

        handler = make_compatibility_evaluated_handler(_SM)
        await handler(_valid_event())

        bus_module.event_bus = original_bus

        async with _SM() as s:
            result = await s.execute(
                text("SELECT * FROM rapport_mesure WHERE cni = :cni ORDER BY generated_at DESC"),
                {"cni": _CLIENT_CNI},
            )
            return result.fetchall()

    rows = _run(run())
    assert len(rows) >= 1
    latest = rows[0]
    assert latest.verdict == "compatible"


# ─────────────────────────────────────────────────────────────────────────────
# Task 32: Event handler error paths
# ─────────────────────────────────────────────────────────────────────────────

def test_handler_missing_adjustment_no_row():
    """missing adjustment_id → no row created. Req 2 AC2"""
    event = _valid_event(adj_id=str(uuid.uuid4()))  # non-existent

    async def run():
        handler = make_compatibility_evaluated_handler(_SM)
        await handler(event)
        async with _SM() as s:
            result = await s.execute(
                text("SELECT COUNT(*) FROM rapport_mesure WHERE adjustment_id = :aid"),
                {"aid": event["adjustment_id"]},
            )
            return result.scalar()

    count = _run(run())
    assert count == 0


def test_handler_negative_measurement_no_row():
    """Negative measurement in adjustment → no row created. Req 2 AC3"""
    neg_adj_id = str(uuid.uuid4())

    async def setup():
        sess_id = str(uuid.uuid4())
        async with _SM() as s:
            await s.execute(text("""
                INSERT OR IGNORE INTO capture_sessions (id, user_id, status)
                VALUES (:sid, :uid, 'success')
            """), {"sid": sess_id, "uid": _CLIENT_CNI})
            await s.execute(text("""
                INSERT INTO measurement_adjustments
                    (id, session_id, fabric_id,
                     raw_bust_cm, raw_waist_cm, raw_hips_cm,
                     bust_ease_cm, waist_ease_cm, hips_ease_cm,
                     adjusted_bust_cm, adjusted_waist_cm, adjusted_hips_cm,
                     ease_source)
                VALUES
                    (:aid, :sid, :fid,
                     86.0, 66.0, 91.0,
                     4.0,  4.0,  4.0,
                     -5.0, 70.0, 95.0,
                     'rule')
            """), {"aid": neg_adj_id, "sid": sess_id, "fid": _FABRIC_ID})
            await s.commit()

    _run(setup())
    event = _valid_event(adj_id=neg_adj_id)

    async def run():
        handler = make_compatibility_evaluated_handler(_SM)
        await handler(event)
        async with _SM() as s:
            result = await s.execute(
                text("SELECT COUNT(*) FROM rapport_mesure WHERE adjustment_id = :aid"),
                {"aid": neg_adj_id},
            )
            return result.scalar()

    count = _run(run())
    assert count == 0


def test_handler_missing_fabric_no_row():
    """Non-existent fabric_id → no row created. Req 4 AC1"""
    event = _valid_event(fabric_id=str(uuid.uuid4()))

    async def run():
        handler = make_compatibility_evaluated_handler(_SM)
        await handler(event)
        async with _SM() as s:
            result = await s.execute(
                text("SELECT COUNT(*) FROM rapport_mesure WHERE fabric_id = :fid"),
                {"fid": event["fabric_id"]},
            )
            return result.scalar()

    count = _run(run())
    assert count == 0


# ─────────────────────────────────────────────────────────────────────────────
# Task 33: Immutability — two events → two distinct rows
# ─────────────────────────────────────────────────────────────────────────────

def test_two_events_create_two_distinct_rows():
    """
    Emitting the same compatibility.evaluated payload twice creates two
    distinct RapportMesure rows (always INSERT, never UPSERT). Req 8 AC2
    """
    unique_cni = "IMM999001"
    unique_adj = str(uuid.uuid4())

    async def setup():
        sess_id = str(uuid.uuid4())
        async with _SM() as s:
            await s.execute(text("""
                INSERT OR IGNORE INTO users (cni, nom, email, mot_de_passe, role)
                VALUES (:cni, 'Immutable', 'imm@example.com', 'h', 'Client')
            """), {"cni": unique_cni})
            await s.execute(text("""
                INSERT OR IGNORE INTO capture_sessions (id, user_id, status)
                VALUES (:sid, :uid, 'success')
            """), {"sid": sess_id, "uid": unique_cni})
            await s.execute(text("""
                INSERT INTO measurement_adjustments
                    (id, session_id, fabric_id,
                     raw_bust_cm, raw_waist_cm, raw_hips_cm,
                     bust_ease_cm, waist_ease_cm, hips_ease_cm,
                     adjusted_bust_cm, adjusted_waist_cm, adjusted_hips_cm)
                VALUES (:aid, :sid, :fid,
                        86.0, 66.0, 91.0, 4.0, 4.0, 4.0, 90.0, 70.0, 95.0)
            """), {"aid": unique_adj, "sid": sess_id, "fid": _FABRIC_ID})
            await s.commit()

    _run(setup())
    event = _valid_event(cni=unique_cni, adj_id=unique_adj)

    async def run():
        handler = make_compatibility_evaluated_handler(_SM)
        await handler(event)
        await handler(event)  # second delivery
        async with _SM() as s:
            result = await s.execute(
                text("SELECT id_report FROM rapport_mesure WHERE cni = :cni"),
                {"cni": unique_cni},
            )
            return result.fetchall()

    rows = _run(run())
    assert len(rows) == 2, f"Expected 2 rows, got {len(rows)}"
    assert rows[0][0] != rows[1][0], "Both rows must have distinct id_report values"


# ─────────────────────────────────────────────────────────────────────────────
# Task 37: Hypothesis — report list ordering invariant
# ─────────────────────────────────────────────────────────────────────────────

@given(
    dates=st.lists(
        st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2025, 12, 31)),
        min_size=2, max_size=8,
    )
)
@settings(max_examples=50, deadline=15_000)
def test_report_list_ordering_invariant(dates: list[datetime]) -> None:
    """
    Property 6: For N reports with arbitrary generated_at timestamps,
    list_reports_for_client() returns them in non-increasing generated_at order.
    Design §Correctness Property 6 · Req 6 AC1
    """
    unique_cni = f"ORD{abs(hash(str(dates)))%100000:05d}"[:9]

    async def run():
        import json
        async with _SM() as s:
            await s.execute(text("""
                INSERT OR IGNORE INTO users (cni, nom, email, mot_de_passe, role)
                VALUES (:cni, 'Order Test', :email, 'h', 'Client')
            """), {"cni": unique_cni, "email": f"{unique_cni}@test.com"})
            await s.execute(
                text("DELETE FROM rapport_mesure WHERE cni = :cni"),
                {"cni": unique_cni},
            )
            snap = json.dumps({
                "adjusted_bust_cm": 90.0, "adjusted_waist_cm": 70.0,
                "adjusted_hips_cm": 95.0, "bust_ease_cm": 4.0,
                "waist_ease_cm": 4.0, "hips_ease_cm": 4.0, "ease_source": "rule",
            })
            for dt in dates:
                ts = dt.strftime("%Y-%m-%d %H:%M:%S")
                await s.execute(text("""
                    INSERT INTO rapport_mesure
                        (id_report, cni, adjustment_id, fabric_id, model_id,
                         verdict, adjusted_measurements, advice, generated_at)
                    VALUES (:rid, :cni, :aid, :fid, :mid,
                            'compatible', :snap, 'Test', :ts)
                """), {
                    "rid": str(uuid.uuid4()), "cni": unique_cni,
                    "aid": _ADJ_ID, "fid": _FABRIC_ID, "mid": _MODEL_ID,
                    "snap": snap, "ts": ts,
                })
            await s.commit()

        service = ReportService()
        async with _SM() as s:
            reports = await service.list_reports_for_client(unique_cni, s)
            return reports

    reports = _run(run())
    assert len(reports) == len(dates)
    for i in range(len(reports) - 1):
        assert reports[i].generated_at >= reports[i + 1].generated_at, (
            f"Ordering violation at index {i}: "
            f"{reports[i].generated_at} < {reports[i+1].generated_at}"
        )


# ── Shared helpers ────────────────────────────────────────────────────────────

async def _create_extra_user(cni: str) -> None:
    async with _SM() as s:
        await s.execute(text("""
            INSERT OR IGNORE INTO users (cni, nom, email, mot_de_passe, role)
            VALUES (:cni, :nom, :email, 'h', 'Client')
        """), {"cni": cni, "nom": f"User {cni}", "email": f"{cni}@test.com"})
        await s.commit()
