"""
Example-based tests — Registration endpoint (POST /auth-catalogues/auth/register).

Covers:
  - Valid registration flow → 201
  - Duplicate CNI → 409
  - Duplicate email → 409
  - Invalid CNI format → 422
  - Invalid email → 422
  - Password < 8 chars → 422
  - nom > 100 chars → 422
  - Missing required fields → 422

Uses the same SQLite + FastAPI TestClient pattern as test_registration.py.

Requirements: 1.1–1.10
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



# ── Shared SQLite helpers ─────────────────────────────────────────────────────

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


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
    """Create SQLite-compatible tables (PostgreSQL regex CHECK stripped)."""
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


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def register_client():
    """Fresh in-memory DB + TestClient for each test."""
    engine, session_maker = _make_engine_and_session()
    _run_sync(_create_tables(engine))
    client = _build_client(engine, session_maker)
    yield client
    app.dependency_overrides.clear()
    _run_sync(engine.dispose())


# ── Valid payload helper ───────────────────────────────────────────────────────

def _valid_payload(**overrides) -> dict:
    base = {
        "cni": "ABC123456",
        "nom": "Alice Dupont",
        "email": "alice@example.com",
        "mot_de_passe": "Secure1234",
        "role": "Client",
    }
    base.update(overrides)
    return base


# ── Tests — happy path ────────────────────────────────────────────────────────

def test_register_valid_returns_201(register_client):
    """
    A well-formed registration request must return 201 Created with the user profile.

    Requirements: 1.1
    """
    resp = register_client.post(
        "/auth-catalogues/auth/register",
        json=_valid_payload(),
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["cni"] == "ABC123456"
    assert body["nom"] == "Alice Dupont"
    assert body["email"] == "alice@example.com"
    assert body["role"] == "Client"
    assert "date_inscription" in body


def test_register_tailor_role_allowed(register_client):
    """Tailor role can be registered successfully."""
    resp = register_client.post(
        "/auth-catalogues/auth/register",
        json=_valid_payload(role="Tailor", cni="XYZ987654", email="tailor@example.com"),
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    assert resp.json()["role"] == "Tailor"


def test_register_admin_role_allowed(register_client):
    """Admin role can be registered successfully."""
    resp = register_client.post(
        "/auth-catalogues/auth/register",
        json=_valid_payload(role="Admin", cni="ADM123456", email="admin@example.com"),
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    assert resp.json()["role"] == "Admin"


# ── Tests — 409 Conflict ─────────────────────────────────────────────────────

def test_register_duplicate_cni_returns_409(register_client):
    """
    Second registration with the same CNI must return 409 with field=cni.

    Requirements: 1.2
    """
    # First registration succeeds
    register_client.post("/auth-catalogues/auth/register", json=_valid_payload())

    # Second registration with same CNI, different email
    resp = register_client.post(
        "/auth-catalogues/auth/register",
        json=_valid_payload(email="other@example.com"),
    )
    assert resp.status_code == 409, f"Expected 409, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", resp.json())
    assert detail.get("error") == "DUPLICATE_RESOURCE"
    assert detail.get("field") == "cni"


def test_register_duplicate_email_returns_409(register_client):
    """
    Second registration with the same email must return 409 with field=email.

    Requirements: 1.3
    """
    # First registration succeeds
    register_client.post("/auth-catalogues/auth/register", json=_valid_payload())

    # Second registration with same email, different CNI
    resp = register_client.post(
        "/auth-catalogues/auth/register",
        json=_valid_payload(cni="DEF789012"),
    )
    assert resp.status_code == 409, f"Expected 409, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", resp.json())
    assert detail.get("error") == "DUPLICATE_RESOURCE"
    assert detail.get("field") == "email"


# ── Tests — 422 Validation errors ────────────────────────────────────────────

def test_register_invalid_cni_too_short_returns_422(register_client):
    """
    CNI shorter than 9 chars must be rejected with 422.

    Requirements: 1.4
    """
    resp = register_client.post(
        "/auth-catalogues/auth/register",
        json=_valid_payload(cni="ABC12"),
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_register_invalid_cni_special_chars_returns_422(register_client):
    """
    CNI with non-alphanumeric characters must be rejected with 422.

    Requirements: 1.4
    """
    resp = register_client.post(
        "/auth-catalogues/auth/register",
        json=_valid_payload(cni="ABC-12345"),
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_register_invalid_cni_too_long_returns_422(register_client):
    """
    CNI longer than 9 chars must be rejected with 422.

    Requirements: 1.4
    """
    resp = register_client.post(
        "/auth-catalogues/auth/register",
        json=_valid_payload(cni="ABCDEFGHIJ"),  # 10 chars
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_register_invalid_email_returns_422(register_client):
    """
    Malformed email must be rejected with 422.

    Requirements: 1.5
    """
    resp = register_client.post(
        "/auth-catalogues/auth/register",
        json=_valid_payload(email="not-an-email"),
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_register_password_too_short_returns_422(register_client):
    """
    Password shorter than 8 chars must be rejected with 422.

    Requirements: 1.6
    """
    resp = register_client.post(
        "/auth-catalogues/auth/register",
        json=_valid_payload(mot_de_passe="Short1"),
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_register_nom_too_long_returns_422(register_client):
    """
    nom longer than 100 chars must be rejected with 422.

    Requirements: 1.7
    """
    resp = register_client.post(
        "/auth-catalogues/auth/register",
        json=_valid_payload(nom="A" * 101),
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_register_missing_cni_returns_422(register_client):
    """Missing cni field must return 422."""
    payload = _valid_payload()
    del payload["cni"]
    resp = register_client.post("/auth-catalogues/auth/register", json=payload)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_register_missing_email_returns_422(register_client):
    """Missing email field must return 422."""
    payload = _valid_payload()
    del payload["email"]
    resp = register_client.post("/auth-catalogues/auth/register", json=payload)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_register_missing_password_returns_422(register_client):
    """Missing mot_de_passe field must return 422."""
    payload = _valid_payload()
    del payload["mot_de_passe"]
    resp = register_client.post("/auth-catalogues/auth/register", json=payload)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_register_missing_role_returns_422(register_client):
    """Missing role field must return 422."""
    payload = _valid_payload()
    del payload["role"]
    resp = register_client.post("/auth-catalogues/auth/register", json=payload)
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_register_invalid_role_returns_422(register_client):
    """
    Role value not in [Client, Tailor, Admin] must return 422.

    Requirements: 1.8
    """
    resp = register_client.post(
        "/auth-catalogues/auth/register",
        json=_valid_payload(role="SuperUser"),
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_register_empty_body_returns_422(register_client):
    """Empty body must return 422."""
    resp = register_client.post("/auth-catalogues/auth/register", json={})
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


# ── Tests — response shape ────────────────────────────────────────────────────

def test_register_response_does_not_include_password(register_client):
    """
    The 201 response must never include the plaintext or hashed password.

    Requirements: 1.10
    """
    resp = register_client.post(
        "/auth-catalogues/auth/register",
        json=_valid_payload(),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "mot_de_passe" not in body
    assert "password" not in body
    assert "hashed" not in body
