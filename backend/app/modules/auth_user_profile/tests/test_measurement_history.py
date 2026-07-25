# Feature: auth-user-profile, Property 5: Mensuration History Ordering and Completeness
"""
Property 5: Mensuration History Ordering and Completeness

For any User with n ≥ 2 Mensuration entries, the list returned by the history
endpoint shall:
  - Contain exactly n records (no omissions, no duplicates).
  - Be ordered by date_mensuration descending:
      entries[i].date_mensuration >= entries[i+1].date_mensuration for all i.

Validates: Requirements 10.1, 10.2, 10.4
Pattern: Invariant — sort order and completeness preserved across arbitrary insertions
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.main import app
from app.modules.auth_user_profile.auth.security import issue_token


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



# ── SQLite in-memory DB helpers ───────────────────────────────────────────────

SQLITE_URL = "sqlite+aiosqlite:///:memory:"
VALID_CLIENT_CNI = "TST000002"


def _make_engine_and_session():
    engine = create_async_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    return engine, session_maker


async def _create_schema(engine) -> None:
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
            CREATE TABLE IF NOT EXISTS token_denylist (
                jti        TEXT     NOT NULL PRIMARY KEY,
                expires_at DATETIME NOT NULL
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS mensuration (
                id_mesure          VARCHAR(36)   NOT NULL PRIMARY KEY,
                cni                VARCHAR(9)    NOT NULL REFERENCES users(cni) ON DELETE CASCADE,
                tour_poitrine      NUMERIC(6,2)  NOT NULL,
                tour_taille        NUMERIC(6,2)  NOT NULL,
                tour_hanches       NUMERIC(6,2)  NOT NULL,
                longueur_bras      NUMERIC(6,2)  NOT NULL,
                hauteur            NUMERIC(6,2)  NOT NULL,
                date_mensuration   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
                source_event_hash  TEXT          UNIQUE
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS photo_profil (
                id_photo    VARCHAR(36) NOT NULL PRIMARY KEY,
                cni         VARCHAR(9)  NOT NULL REFERENCES users(cni) ON DELETE CASCADE,
                url_photo   TEXT        NOT NULL,
                date_upload DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP
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
            CREATE TABLE IF NOT EXISTS tailor_client_assignment (
                tailor_cni  VARCHAR(9) NOT NULL REFERENCES users(cni) ON DELETE CASCADE,
                client_cni  VARCHAR(9) NOT NULL REFERENCES users(cni) ON DELETE CASCADE,
                assigned_at DATETIME   NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (tailor_cni, client_cni)
            )
        """))
        await conn.execute(text("""
            INSERT OR IGNORE INTO users (cni, nom, email, mot_de_passe, role)
            VALUES (:cni, 'History Client', 'historyclient@example.com', 'hashed', 'Client')
        """), {"cni": VALID_CLIENT_CNI})


# ── Module-level engine (shared across all hypothesis runs) ──────────────────
# We keep one engine/session_maker at module scope so dependency override is stable.

_ENGINE = None
_SESSION_MAKER = None


@pytest.fixture(scope="module", autouse=True)
def history_db():
    global _ENGINE, _SESSION_MAKER
    _ENGINE, _SESSION_MAKER = _make_engine_and_session()
    _run_sync(_create_schema(_ENGINE))

    async def override_get_db():
        async with _SESSION_MAKER() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    _run_sync(_ENGINE.dispose())


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _seed_mensurations(dates: list[datetime]) -> None:
    """
    Insert n mensuration rows for VALID_CLIENT_CNI with the given dates.
    Uses raw SQL to control date_mensuration precisely (bypasses ORM defaults).
    Clears existing rows first so each hypothesis run starts from a clean state.
    """
    async with _SESSION_MAKER() as session:
        # Clear existing records for the test user
        await session.execute(
            text("DELETE FROM mensuration WHERE cni = :cni"),
            {"cni": VALID_CLIENT_CNI},
        )
        for dt in dates:
            # Normalise to UTC, format as ISO string for SQLite
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            await session.execute(
                text("""
                    INSERT INTO mensuration
                        (id_mesure, cni, tour_poitrine, tour_taille, tour_hanches,
                         longueur_bras, hauteur, date_mensuration)
                    VALUES (:id, :cni, 90.0, 70.0, 95.0, 60.0, 165.0, :dt)
                """),
                {"id": str(uuid.uuid4()), "cni": VALID_CLIENT_CNI, "dt": dt_str},
            )
        await session.commit()


# ── Strategy ──────────────────────────────────────────────────────────────────

date_list_strategy = st.lists(
    st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2025, 12, 31),
    ),
    min_size=2,
    max_size=10,
)


# ── Property 5 ────────────────────────────────────────────────────────────────

@given(dates=date_list_strategy)
@settings(max_examples=50)
def test_mensuration_history_ordering_and_completeness(dates: list[datetime]) -> None:
    """
    **Validates: Requirements 10.1, 10.2, 10.4**

    Seeds n mensuration records with the given dates, then calls
    GET /auth-catalogues/users/me/mensurations and asserts:
      1. Exactly n records are returned.
      2. Records are ordered by date_mensuration descending.
    """
    n = len(dates)

    # Seed records via raw SQL (controls date_mensuration precisely)
    _run_sync(_seed_mensurations(dates))

    token = issue_token(cni=VALID_CLIENT_CNI, role="Client")
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client:
        response = client.get(
            "/auth-catalogues/users/me/mensurations",
            headers=headers,
        )

    assert response.status_code == 200, (
        f"Expected HTTP 200 but got {response.status_code}. Body: {response.text}"
    )

    returned = response.json()

    # Completeness: exactly n records
    assert len(returned) == n, (
        f"Expected {n} records but got {len(returned)}. Seeded dates: {dates}"
    )

    # Ordering: descending by date_mensuration
    for i in range(len(returned) - 1):
        dt_i = datetime.fromisoformat(returned[i]["date_mensuration"])
        dt_j = datetime.fromisoformat(returned[i + 1]["date_mensuration"])
        assert dt_i >= dt_j, (
            f"Ordering violation at index {i}: "
            f"{dt_i} < {dt_j}. Full list dates: {[r['date_mensuration'] for r in returned]}"
        )


# ── Example-based tests (Task 29) ─────────────────────────────────────────────
# These tests use a separately-registered Client so they do not conflict with the
# raw-SQL seeded user used in the property test (which stores 'Client' the value
# but the ORM UserModel Enum expects 'CLIENT' the name).

# CNI used exclusively by example-based tests (different from VALID_CLIENT_CNI)
_EXAMPLE_CLIENT_CNI = "MSR111111"
_EXAMPLE_CLIENT_EMAIL = "example_meas_client@example.com"


def _ensure_example_client() -> None:
    """Register _EXAMPLE_CLIENT_CNI via the API (idempotent)."""
    with TestClient(app, raise_server_exceptions=False) as c:
        c.post(
            "/auth-catalogues/auth/register",
            json={
                "cni": _EXAMPLE_CLIENT_CNI,
                "nom": "Example Meas Client",
                "email": _EXAMPLE_CLIENT_EMAIL,
                "mot_de_passe": "Secure1234",
                "role": "Client",
            },
        )


def test_create_mensuration_valid_returns_201() -> None:
    """
    A Client can POST a valid measurement set and gets 201 with all 7 fields.
    Requirements: 8.1, 8.6
    """
    _ensure_example_client()
    token = issue_token(cni=_EXAMPLE_CLIENT_CNI, role="Client")
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "tour_poitrine": 90.5,
        "tour_taille": 70.0,
        "tour_hanches": 95.0,
        "longueur_bras": 60.0,
        "hauteur": 165.0,
    }

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/auth-catalogues/users/me/mensurations",
            json=payload,
            headers=headers,
        )

    assert response.status_code == 201, (
        f"Expected 201, got {response.status_code}: {response.text}"
    )
    body = response.json()
    for field in ("id_mesure", "tour_poitrine", "tour_taille", "tour_hanches",
                  "longueur_bras", "hauteur", "date_mensuration"):
        assert field in body, f"Missing field '{field}' in response: {body}"


def test_create_mensuration_tailor_forbidden_returns_403() -> None:
    """
    A Tailor attempting POST /users/me/mensurations receives 403.
    Requirements: 5.6, 8.1
    """
    tailor_cni = "TLR111099"
    tailor_email = "tailor_meas_ex@example.com"

    # Register the Tailor via the API so the user exists with correct ORM role
    with TestClient(app, raise_server_exceptions=False) as client:
        client.post(
            "/auth-catalogues/auth/register",
            json={
                "cni": tailor_cni,
                "nom": "Tailor Meas Test",
                "email": tailor_email,
                "mot_de_passe": "Secure1234",
                "role": "Tailor",
            },
        )

    token = issue_token(cni=tailor_cni, role="Tailor")
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/auth-catalogues/users/me/mensurations",
            json={
                "tour_poitrine": 88.0,
                "tour_taille": 66.0,
                "tour_hanches": 92.0,
                "longueur_bras": 58.0,
                "hauteur": 170.0,
            },
            headers=headers,
        )

    assert response.status_code == 403, (
        f"Expected 403 for Tailor POST measurement, got {response.status_code}: {response.text}"
    )


def test_get_history_empty_returns_200_empty_list() -> None:
    """
    A freshly-registered Client with no measurements gets 200 and an empty list.
    Requirements: 10.5
    """
    new_cni = "MSR222099"
    new_email = "empty_hist_ex@example.com"

    with TestClient(app, raise_server_exceptions=False) as client:
        client.post(
            "/auth-catalogues/auth/register",
            json={
                "cni": new_cni,
                "nom": "Empty History Client",
                "email": new_email,
                "mot_de_passe": "Secure1234",
                "role": "Client",
            },
        )

    token = issue_token(cni=new_cni, role="Client")
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/auth-catalogues/users/me/mensurations",
            headers=headers,
        )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )
    assert response.json() == [], f"Expected empty list, got: {response.json()}"


def test_get_history_full_field_set() -> None:
    """
    The history endpoint returns all 7 required fields for each entry.
    Requirements: 10.4
    """
    _ensure_example_client()
    token = issue_token(cni=_EXAMPLE_CLIENT_CNI, role="Client")
    headers = {"Authorization": f"Bearer {token}"}

    # Create at least one measurement via the API to ensure ORM-correct data
    with TestClient(app, raise_server_exceptions=False) as client:
        client.post(
            "/auth-catalogues/users/me/mensurations",
            json={
                "tour_poitrine": 91.0,
                "tour_taille": 71.0,
                "tour_hanches": 96.0,
                "longueur_bras": 61.0,
                "hauteur": 166.0,
            },
            headers=headers,
        )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/auth-catalogues/users/me/mensurations",
            headers=headers,
        )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )

    entries = response.json()
    assert len(entries) >= 1, "Expected at least 1 measurement in history"

    required_fields = (
        "id_mesure", "tour_poitrine", "tour_taille",
        "tour_hanches", "longueur_bras", "hauteur", "date_mensuration",
    )
    for entry in entries:
        for field in required_fields:
            assert field in entry, (
                f"Missing required field '{field}' in measurement entry: {entry}"
            )
