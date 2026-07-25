"""
Property-based tests — Property 7: Role-Based Access — Authorisation Consistency.

# Feature: auth-user-profile, Property 7: Role-Based Access — Authorisation Consistency
# Validates: Requirements 5.4, 5.5, 5.6, 13.4

Pattern: Metamorphic — for every (role, endpoint) pair where role is NOT in the
endpoint's authorised_roles set, every request must be rejected with HTTP 403,
regardless of any other attributes of the user.

Strategy:
  - st.sampled_from(["Client", "Tailor", "Admin"]) × st.sampled_from(PROTECTED_ENDPOINTS)
  - For each pair: if role NOT in authorised_roles → assert response.status_code == 403
  - Uses issue_token(cni="TST123456", role=role) — no DB interaction needed for RBAC check
    (the role check happens before any DB calls in the dependency chain)
  - max_examples=100

SQLite TestClient pattern:
  The FastAPI TestClient is backed by a minimal in-memory SQLite DB that has the
  token_denylist table so get_current_user can complete its denylist check before
  the require_role dependency fires.
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



# ── Protected endpoint registry ───────────────────────────────────────────────
# Each tuple: (HTTP method, path, set of roles that ARE authorised)

PROTECTED_ENDPOINTS = [
    # (method, path, authorised_roles)
    ("GET",   "/auth-catalogues/users/me",                          {"Client", "Tailor", "Admin"}),
    ("PATCH", "/auth-catalogues/users/me",                          {"Client", "Tailor", "Admin"}),
    ("GET",   "/auth-catalogues/users/me/photos",                   {"Client", "Tailor", "Admin"}),
    ("GET",   "/auth-catalogues/users/me/reports",                  {"Client", "Tailor", "Admin"}),
    ("GET",   "/auth-catalogues/admin/users",                       {"Admin"}),
    ("PATCH", "/auth-catalogues/admin/users/TST123456/role",        {"Admin"}),
    ("PATCH", "/auth-catalogues/admin/users/TST123456/deactivate",  {"Admin"}),
]

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


# ── SQLite helpers ─────────────────────────────────────────────────────────────

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
    """Create the minimal schema needed for the RBAC test (token_denylist + users)."""
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


def _build_test_app(engine, session_maker) -> None:
    """Override get_db with the in-memory SQLite session factory."""

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


# ── Module-level fixture: one DB for the whole test module ────────────────────

@pytest.fixture(scope="module", autouse=True)
def rbac_db():
    """
    Create a shared in-memory SQLite DB for all RBAC tests in this module.
    The DB only needs to hold schema (no user rows); the role check fires before
    any DB lookup for the unauthorised-role cases.
    """
    engine, session_maker = _make_engine_and_session()
    _run_sync(_create_tables(engine))
    _build_test_app(engine, session_maker)
    yield
    app.dependency_overrides.clear()
    _run_sync(engine.dispose())


# ── Property 7 ────────────────────────────────────────────────────────────────

@given(
    role=st.sampled_from(["Client", "Tailor", "Admin"]),
    endpoint=st.sampled_from(PROTECTED_ENDPOINTS),
)
@settings(max_examples=100)
def test_rbac_unauthorised_roles_always_receive_403(
    role: str,
    endpoint: tuple[str, str, set[str]],
) -> None:
    """
    **Validates: Requirements 5.4, 5.5, 5.6, 13.4**

    For any (role, endpoint) pair where role is NOT in the endpoint's authorised_roles,
    every request must be rejected with HTTP 403.

    Token is issued for cni="TST123456" with the given role.  The role check in
    require_role fires before any repository calls, so no user row is needed in the DB.
    """
    method, path, authorised_roles = endpoint

    # Only exercise unauthorised combinations
    if role in authorised_roles:
        return  # skip — this role IS allowed; not the case under test

    token = issue_token(cni="TST123456", role=role)
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client:
        response = getattr(client, method.lower())(path, headers=headers)

    assert response.status_code == 403, (
        f"Expected 403 for role='{role}' on {method} {path}, "
        f"but got {response.status_code}. "
        f"Authorised roles for this endpoint: {authorised_roles}."
    )


# ── Sanity: authorised roles must NOT get 403 ─────────────────────────────────

def test_authorised_roles_do_not_get_403_on_admin_list_users() -> None:
    """
    An Admin token on GET /admin/users must not return 403.
    (It may return 404/500 because there's no data, but not 403.)
    """
    token = issue_token(cni="TST123456", role="Admin")
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client:
        response = client.get("/auth-catalogues/admin/users", headers=headers)

    assert response.status_code != 403, (
        f"Admin got 403 on GET /admin/users — RBAC is misconfigured. "
        f"Status: {response.status_code}"
    )


def test_authorised_roles_do_not_get_403_on_users_me() -> None:
    """
    A Client token on GET /users/me must not return 403.
    (It may return 404 because there's no user row, but not 403.)
    """
    token = issue_token(cni="TST123456", role="Client")
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client:
        response = client.get("/auth-catalogues/users/me", headers=headers)

    assert response.status_code != 403, (
        f"Client got 403 on GET /users/me — RBAC is misconfigured. "
        f"Status: {response.status_code}"
    )
