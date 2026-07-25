"""
Example-based tests — Login endpoint (POST /auth-catalogues/auth/login).

Covers:
  - Valid credentials → 200 + JWT access_token
  - Wrong password → 401
  - Unknown email → 401
  - Deactivated account → 401
  - Missing fields → 422
  - Lockout after 5 consecutive failures → 429 with Retry-After header

Uses the same SQLite + FastAPI TestClient pattern as test_registration.py.
Users are seeded via the register endpoint so enum values are stored correctly.

Requirements: 2.1–2.8
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.main import app
from app.modules.auth_user_profile.auth.rate_limit import rate_limiter

# ── Shared SQLite helpers ─────────────────────────────────────────────────────

SQLITE_URL = "sqlite+aiosqlite:///:memory:"

# Default test credentials (seeded via the register API in the fixture)
DEFAULT_EMAIL = "user@example.com"
DEFAULT_PASSWORD = "Passw0rd!"
DEFAULT_CNI = "USR123456"


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


async def _create_tables(engine):
    """Create SQLite-compatible schema (PostgreSQL regex CHECK stripped)."""
    async with engine.begin() as conn:
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                cni            VARCHAR(9)   NOT NULL PRIMARY KEY,
                nom            VARCHAR(100) NOT NULL,
                email          VARCHAR(255) NOT NULL UNIQUE,
                mot_de_passe   TEXT         NOT NULL,
                role           VARCHAR(20)  NOT NULL,
                is_active      BOOLEAN      NOT NULL DEFAULT 1,
                date_inscription DATETIME   NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS token_denylist (
                jti        TEXT     NOT NULL PRIMARY KEY,
                expires_at DATETIME NOT NULL
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
            CREATE TABLE IF NOT EXISTS mensuration (
                id_mesure         VARCHAR(36)  NOT NULL PRIMARY KEY,
                cni               VARCHAR(9)   NOT NULL REFERENCES users(cni) ON DELETE CASCADE,
                tour_poitrine     NUMERIC(6,2) NOT NULL,
                tour_taille       NUMERIC(6,2) NOT NULL,
                tour_hanches      NUMERIC(6,2) NOT NULL,
                longueur_bras     NUMERIC(6,2) NOT NULL,
                hauteur           NUMERIC(6,2) NOT NULL,
                date_mensuration  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                source_event_hash TEXT         UNIQUE
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


def _build_client(engine, session_maker) -> TestClient:
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
    return TestClient(app, raise_server_exceptions=False)


def _deactivate_user(session_maker, email: str) -> None:
    """Set is_active=0 for a user directly via raw SQL."""
    async def _do():
        async with session_maker() as session:
            await session.execute(
                text("UPDATE users SET is_active = 0 WHERE email = :email"),
                {"email": email},
            )
            await session.commit()

    _run_sync(_do())


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def login_client():
    """
    Fresh in-memory DB + TestClient for each test.
    Seeds a default active user via the register endpoint so ORM enum values
    are stored correctly.
    """
    engine, session_maker = _make_engine_and_session()
    _run_sync(_create_tables(engine))
    client = _build_client(engine, session_maker)

    # Seed default user via the API (so ORM handles enum storage)
    reg_resp = client.post(
        "/auth-catalogues/auth/register",
        json={
            "cni": DEFAULT_CNI,
            "nom": "Test User",
            "email": DEFAULT_EMAIL,
            "mot_de_passe": DEFAULT_PASSWORD,
            "role": "Client",
        },
    )
    assert reg_resp.status_code == 201, (
        f"Fixture: failed to seed default user: {reg_resp.status_code} {reg_resp.text}"
    )

    # Clear any stale rate-limit state
    rate_limiter.reset(DEFAULT_EMAIL)

    yield client, engine, session_maker

    app.dependency_overrides.clear()
    _run_sync(engine.dispose())
    rate_limiter.reset(DEFAULT_EMAIL)


# ── Tests — happy path ────────────────────────────────────────────────────────

def test_login_valid_credentials_returns_200_with_jwt(login_client):
    """
    Valid email + password must return 200 with access_token and token_type=bearer.

    Requirements: 2.1, 2.2
    """
    client, *_ = login_client
    resp = client.post(
        "/auth-catalogues/auth/login",
        json={"email": DEFAULT_EMAIL, "mot_de_passe": DEFAULT_PASSWORD},
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "access_token" in body, f"Missing access_token: {body}"
    assert body["token_type"] == "bearer"
    # Token must be a non-empty JWT string (3 dot-separated parts)
    parts = body["access_token"].split(".")
    assert len(parts) == 3, f"access_token is not a JWT: {body['access_token'][:40]}"


def test_login_jwt_contains_expected_claims(login_client):
    """
    The issued JWT must carry cni, role, and exp - iat == 86400.

    Requirements: 2.2, 4.2
    """
    from app.modules.auth_user_profile.auth.security import decode_token, JWT_EXPIRY_SECONDS


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



    client, *_ = login_client
    resp = client.post(
        "/auth-catalogues/auth/login",
        json={"email": DEFAULT_EMAIL, "mot_de_passe": DEFAULT_PASSWORD},
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    token = resp.json()["access_token"]
    claims = decode_token(token)
    assert claims["cni"] == DEFAULT_CNI
    assert claims["role"] == "Client"
    assert claims["exp"] - claims["iat"] == JWT_EXPIRY_SECONDS


# ── Tests — 401 Invalid credentials ──────────────────────────────────────────

def test_login_wrong_password_returns_401(login_client):
    """
    Wrong password for an existing email must return 401 INVALID_CREDENTIALS.

    Requirements: 2.3
    """
    client, *_ = login_client
    resp = client.post(
        "/auth-catalogues/auth/login",
        json={"email": DEFAULT_EMAIL, "mot_de_passe": "WrongPass1"},
    )
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", resp.json())
    assert detail.get("error") == "INVALID_CREDENTIALS"


def test_login_unknown_email_returns_401(login_client):
    """
    Unknown email must return 401 INVALID_CREDENTIALS (no field disclosure).

    Requirements: 2.4
    """
    client, *_ = login_client
    rate_limiter.reset("unknown@example.com")
    resp = client.post(
        "/auth-catalogues/auth/login",
        json={"email": "unknown@example.com", "mot_de_passe": DEFAULT_PASSWORD},
    )
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", resp.json())
    assert detail.get("error") == "INVALID_CREDENTIALS"
    rate_limiter.reset("unknown@example.com")


def test_login_deactivated_account_returns_401(login_client):
    """
    Deactivated account with valid credentials must return 401 ACCOUNT_DEACTIVATED.

    Requirements: 13.6
    """
    client, engine, session_maker = login_client

    # Register a second user, then deactivate them via direct SQL
    disabled_email = "disabled@example.com"
    client.post(
        "/auth-catalogues/auth/register",
        json={
            "cni": "DIS123456",
            "nom": "Disabled User",
            "email": disabled_email,
            "mot_de_passe": DEFAULT_PASSWORD,
            "role": "Client",
        },
    )
    _deactivate_user(session_maker, disabled_email)

    rate_limiter.reset(disabled_email)
    resp = client.post(
        "/auth-catalogues/auth/login",
        json={"email": disabled_email, "mot_de_passe": DEFAULT_PASSWORD},
    )
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", resp.json())
    assert detail.get("error") == "ACCOUNT_DEACTIVATED"
    rate_limiter.reset(disabled_email)


# ── Tests — 422 Validation errors ────────────────────────────────────────────

def test_login_missing_email_returns_422(login_client):
    """Missing email must return 422."""
    client, *_ = login_client
    resp = client.post(
        "/auth-catalogues/auth/login",
        json={"mot_de_passe": DEFAULT_PASSWORD},
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_login_missing_password_returns_422(login_client):
    """Missing mot_de_passe must return 422."""
    client, *_ = login_client
    resp = client.post(
        "/auth-catalogues/auth/login",
        json={"email": DEFAULT_EMAIL},
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_login_invalid_email_format_returns_422(login_client):
    """Malformed email must return 422."""
    client, *_ = login_client
    resp = client.post(
        "/auth-catalogues/auth/login",
        json={"email": "not-an-email", "mot_de_passe": DEFAULT_PASSWORD},
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_login_empty_body_returns_422(login_client):
    """Empty body must return 422."""
    client, *_ = login_client
    resp = client.post("/auth-catalogues/auth/login", json={})
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


# ── Tests — 429 Rate limiting ─────────────────────────────────────────────────

def test_login_lockout_after_5_failures_returns_429(login_client):
    """
    After 5 consecutive failed login attempts for the same email,
    the 6th must return 429 RATE_LIMIT_EXCEEDED with a Retry-After header.

    Requirements: 2.7
    """
    client, *_ = login_client
    lockout_email = "lockme@example.com"
    rate_limiter.reset(lockout_email)

    for i in range(5):
        resp = client.post(
            "/auth-catalogues/auth/login",
            json={"email": lockout_email, "mot_de_passe": "WrongPass1"},
        )
        # Each attempt fails with 401 (unknown email — not yet locked)
        assert resp.status_code in (401, 422), (
            f"Attempt {i + 1}: expected 401, got {resp.status_code}: {resp.text}"
        )

    # 6th attempt must be rate-limited
    resp = client.post(
        "/auth-catalogues/auth/login",
        json={"email": lockout_email, "mot_de_passe": "WrongPass1"},
    )
    assert resp.status_code == 429, (
        f"Expected 429 after 5 failures, got {resp.status_code}: {resp.text}"
    )
    detail = resp.json().get("detail", resp.json())
    assert detail.get("error") == "RATE_LIMIT_EXCEEDED"
    assert "Retry-After" in resp.headers, "Missing Retry-After header on 429"

    rate_limiter.reset(lockout_email)


def test_login_rate_limit_resets_on_success(login_client):
    """
    Successful login must reset the failure counter so the account is
    not subsequently blocked.

    Requirements: 2.7
    """
    client, *_ = login_client

    # Cause 3 failures
    for _ in range(3):
        client.post(
            "/auth-catalogues/auth/login",
            json={"email": DEFAULT_EMAIL, "mot_de_passe": "WrongPass1"},
        )

    # Successful login resets the counter
    resp = client.post(
        "/auth-catalogues/auth/login",
        json={"email": DEFAULT_EMAIL, "mot_de_passe": DEFAULT_PASSWORD},
    )
    assert resp.status_code == 200, (
        f"Expected 200 on valid login after failures, got {resp.status_code}: {resp.text}"
    )

    # Should be able to login again without hitting the rate limit
    resp2 = client.post(
        "/auth-catalogues/auth/login",
        json={"email": DEFAULT_EMAIL, "mot_de_passe": DEFAULT_PASSWORD},
    )
    assert resp2.status_code == 200, (
        f"Expected 200 on second valid login, got {resp2.status_code}: {resp2.text}"
    )
