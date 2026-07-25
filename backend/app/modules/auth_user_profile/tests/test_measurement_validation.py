# Feature: auth-user-profile, Property 4: Measurement Validation — Exhaustive Bad-Input Rejection
"""
Property 4: Measurement Validation — Exhaustive Bad-Input Rejection

For any Mensuration creation request where AT LEAST ONE of the five measurement
fields is ≤ 0 or > 300 cm, the Measurement_Service SHALL always reject the request
with HTTP 422 and SHALL NOT create a Mensuration record.

Validates: Requirements 8.3, 8.4, 9.2
Pattern: Error Conditions — exhaustive bad-input rejection
"""
from __future__ import annotations

import asyncio

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

# A fixed valid CNI that will exist in the DB so any 404 is not from a missing user
VALID_CLIENT_CNI = "TST000001"


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
    """Create the minimal schema needed for measurement validation tests."""
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
        # Seed the client user so we can reach the service (not get 404 for missing user)
        await conn.execute(text("""
            INSERT OR IGNORE INTO users (cni, nom, email, mot_de_passe, role)
            VALUES (:cni, 'Test Client', 'testclient@example.com', 'hashed', 'Client')
        """), {"cni": VALID_CLIENT_CNI})


# ── Module-level fixture ──────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def validation_db():
    engine, session_maker = _make_engine_and_session()
    _run_sync(_create_schema(engine))

    async def override_get_db():
        async with session_maker() as session:
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
    _run_sync(engine.dispose())


# ── Hypothesis strategies ─────────────────────────────────────────────────────

# Valid values: (0, 300]
valid_value = st.floats(min_value=0.01, max_value=299.99, allow_nan=False)

# Invalid values: ≤ 0 or > 300
invalid_low = st.floats(max_value=0.0, allow_nan=False, allow_infinity=False)
invalid_high = st.floats(min_value=300.01, allow_nan=False, allow_infinity=False)
invalid_value = st.one_of(invalid_low, invalid_high)

FIELD_NAMES = ["tour_poitrine", "tour_taille", "tour_hanches", "longueur_bras", "hauteur"]


def _bad_input_strategy():
    """
    Build a dict of 5 measurement values where AT LEAST ONE is invalid.
    One field is drawn from invalid_value; the rest from valid_value.
    The 'bad' field is chosen by st.sampled_from to exercise all five.
    """
    @st.composite
    def _build(draw):
        bad_field = draw(st.sampled_from(FIELD_NAMES))
        result = {}
        for field in FIELD_NAMES:
            if field == bad_field:
                result[field] = draw(invalid_value)
            else:
                result[field] = draw(valid_value)
        return result

    return _build()


# ── Property 4 ────────────────────────────────────────────────────────────────

@given(bad_payload=_bad_input_strategy())
@settings(max_examples=100, deadline=None)
def test_measurement_bad_input_always_rejected(bad_payload: dict) -> None:
    """
    **Validates: Requirements 8.3, 8.4, 9.2**

    For any Mensuration creation request where at least one value is ≤ 0 or > 300,
    the endpoint must return 422 and must NOT persist any record.
    """
    token = issue_token(cni=VALID_CLIENT_CNI, role="Client")
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client:
        response = client.post(
            "/auth-catalogues/users/me/mensurations",
            json=bad_payload,
            headers=headers,
        )

    assert response.status_code == 422, (
        f"Expected HTTP 422 for invalid payload {bad_payload}, "
        f"but got {response.status_code}. Body: {response.text}"
    )
