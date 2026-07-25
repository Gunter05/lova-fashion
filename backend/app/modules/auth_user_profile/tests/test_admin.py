"""
Example-based tests — Admin endpoints.

Covers:
  GET  /auth-catalogues/admin/users               — list all users
  PATCH /auth-catalogues/admin/users/{cni}/role   — update role
  PATCH /auth-catalogues/admin/users/{cni}/deactivate — deactivate account

Uses the same SQLite + FastAPI TestClient pattern as other tests.
An Admin and a Client user are registered via the API in the module fixture.

Requirements: 5.3, 5.6, 13.1–13.7
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
from app.modules.auth_catalogues.auth.security import issue_token

# ── SQLite helpers ────────────────────────────────────────────────────────────

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


async def _create_tables(engine) -> None:
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
            CREATE TABLE IF NOT EXISTS photo_profil (
                id_photo    VARCHAR(36) NOT NULL PRIMARY KEY,
                cni         VARCHAR(9)  NOT NULL REFERENCES users(cni) ON DELETE CASCADE,
                url_photo   TEXT        NOT NULL,
                date_upload DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS mensuration (
                id_mesure          VARCHAR(36)  NOT NULL PRIMARY KEY,
                cni                VARCHAR(9)   NOT NULL REFERENCES users(cni) ON DELETE CASCADE,
                tour_poitrine      NUMERIC(6,2) NOT NULL,
                tour_taille        NUMERIC(6,2) NOT NULL,
                tour_hanches       NUMERIC(6,2) NOT NULL,
                longueur_bras      NUMERIC(6,2) NOT NULL,
                hauteur            NUMERIC(6,2) NOT NULL,
                date_mensuration   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                source_event_hash  TEXT         UNIQUE
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


# ── Module-level fixture ──────────────────────────────────────────────────────

_ENGINE = None
_SESSION_MAKER = None

_ADMIN_CNI = "ADM100001"
_ADMIN_EMAIL = "admin_test@example.com"
_ADMIN_TOKEN = None

_CLIENT_CNI = "CLT100001"
_CLIENT_EMAIL = "client_admin_test@example.com"

_ADMIN2_CNI = "ADM100002"
_ADMIN2_EMAIL = "admin2_test@example.com"

# A dedicated CNI for deactivation tests (separate from role-change target)
_DEACT_CNI = "DET100001"
_DEACT_EMAIL = "deact_target@example.com"


@pytest.fixture(scope="module", autouse=True)
def admin_db():
    global _ENGINE, _SESSION_MAKER, _ADMIN_TOKEN

    _ENGINE, _SESSION_MAKER = _make_engine_and_session()
    asyncio.get_event_loop().run_until_complete(_create_tables(_ENGINE))

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

    _ADMIN_TOKEN = issue_token(cni=_ADMIN_CNI, role="Admin")

    with TestClient(app, raise_server_exceptions=False) as c:
        # Register Admin user
        r = c.post(
            "/auth-catalogues/auth/register",
            json={
                "cni": _ADMIN_CNI,
                "nom": "Admin User",
                "email": _ADMIN_EMAIL,
                "mot_de_passe": "Secure1234",
                "role": "Admin",
            },
        )
        assert r.status_code == 201, f"Fixture: admin register failed: {r.text}"

        # Register a second Admin (for role-change protection test)
        r = c.post(
            "/auth-catalogues/auth/register",
            json={
                "cni": _ADMIN2_CNI,
                "nom": "Admin Two",
                "email": _ADMIN2_EMAIL,
                "mot_de_passe": "Secure1234",
                "role": "Admin",
            },
        )
        assert r.status_code == 201, f"Fixture: admin2 register failed: {r.text}"

        # Register a Client user (role-change target)
        r = c.post(
            "/auth-catalogues/auth/register",
            json={
                "cni": _CLIENT_CNI,
                "nom": "Client For Admin",
                "email": _CLIENT_EMAIL,
                "mot_de_passe": "Secure1234",
                "role": "Client",
            },
        )
        assert r.status_code == 201, f"Fixture: client register failed: {r.text}"

        # Register a deactivation target
        r = c.post(
            "/auth-catalogues/auth/register",
            json={
                "cni": _DEACT_CNI,
                "nom": "Deactivation Target",
                "email": _DEACT_EMAIL,
                "mot_de_passe": "Secure1234",
                "role": "Client",
            },
        )
        assert r.status_code == 201, f"Fixture: deact register failed: {r.text}"

    yield

    app.dependency_overrides.clear()
    asyncio.get_event_loop().run_until_complete(_ENGINE.dispose())


def _admin_headers() -> dict:
    return {"Authorization": f"Bearer {_ADMIN_TOKEN}"}


def _client_headers() -> dict:
    return {"Authorization": f"Bearer {issue_token(cni=_CLIENT_CNI, role='Client')}"}


# ── GET /admin/users ──────────────────────────────────────────────────────────

def test_list_users_as_admin_returns_200():
    """
    Admin can list all users and gets back a non-empty list with full fields.
    Requirements: 13.1
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/auth-catalogues/admin/users", headers=_admin_headers())
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    # Each entry must have the required fields
    first = body[0]
    for field in ("cni", "nom", "email", "role", "is_active", "date_inscription"):
        assert field in first, f"Missing field '{field}' in user list entry: {first}"


def test_list_users_as_client_returns_403():
    """
    A Client attempting GET /admin/users receives 403.
    Requirements: 5.6, 13.1
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/auth-catalogues/admin/users", headers=_client_headers())
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"


# ── PATCH /admin/users/{cni}/role ─────────────────────────────────────────────

def test_update_role_success_returns_200():
    """
    Admin can update a non-Admin user's role.
    Requirements: 13.2
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.patch(
            f"/auth-catalogues/admin/users/{_CLIENT_CNI}/role",
            headers=_admin_headers(),
            json={"role": "Tailor"},
        )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["cni"] == _CLIENT_CNI
    assert body["role"] == "Tailor"


def test_update_role_admin_on_admin_returns_403():
    """
    Attempting to change the role of an Admin user returns 403.
    Requirements: 13.4
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.patch(
            f"/auth-catalogues/admin/users/{_ADMIN2_CNI}/role",
            headers=_admin_headers(),
            json={"role": "Client"},
        )
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", resp.json())
    assert detail.get("error") == "ADMIN_ROLE_PROTECTED"


def test_update_role_invalid_role_returns_422():
    """
    PATCH with an unknown role value returns 422.
    Requirements: 13.3
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.patch(
            f"/auth-catalogues/admin/users/{_CLIENT_CNI}/role",
            headers=_admin_headers(),
            json={"role": "SuperUser"},
        )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_update_role_not_found_returns_404():
    """
    PATCH on a CNI that doesn't exist returns 404.
    Requirements: 13.2
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.patch(
            "/auth-catalogues/admin/users/ZZZ999999/role",
            headers=_admin_headers(),
            json={"role": "Client"},
        )
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"


# ── PATCH /admin/users/{cni}/deactivate ───────────────────────────────────────

def test_deactivate_user_success_returns_200():
    """
    Admin can deactivate an active user; returns 200.
    Requirements: 13.5
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.patch(
            f"/auth-catalogues/admin/users/{_DEACT_CNI}/deactivate",
            headers=_admin_headers(),
        )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


def test_deactivate_user_idempotent_returns_200():
    """
    Deactivating an already-inactive user returns 200 (idempotent).
    Requirements: 13.7
    """
    # _DEACT_CNI was deactivated in the previous test; deactivate again
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.patch(
            f"/auth-catalogues/admin/users/{_DEACT_CNI}/deactivate",
            headers=_admin_headers(),
        )
    assert resp.status_code == 200, f"Expected 200 (idempotent), got {resp.status_code}: {resp.text}"


def test_deactivate_user_as_non_admin_returns_403():
    """
    A Client attempting to deactivate a user receives 403.
    Requirements: 5.6
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.patch(
            f"/auth-catalogues/admin/users/{_DEACT_CNI}/deactivate",
            headers=_client_headers(),
        )
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"


def test_deactivate_user_not_found_returns_404():
    """
    Attempting to deactivate a non-existent CNI returns 404.
    Requirements: 13.5
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.patch(
            "/auth-catalogues/admin/users/ZZZ888888/deactivate",
            headers=_admin_headers(),
        )
    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
