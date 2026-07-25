"""
Example-based tests — Profile_Service endpoints.

Covers:
  GET  /auth-catalogues/users/me        — get own profile
  PATCH /auth-catalogues/users/me       — update profile (success, conflict, validation, immutable)
  POST  /auth-catalogues/users/me/photos — photo upload (success, wrong MIME, empty, too large, storage down)
  GET   /auth-catalogues/users/me/photos — photo history (populated + empty)
  GET   /auth-catalogues/users/me/reports — report history (empty)

Uses the same SQLite + FastAPI TestClient pattern as test_auth_register.py.
Photos: SupabaseStorage.upload is patched via a direct storage= kwarg injected
        by monkey-patching the router to use a test-safe path.

Requirements: 5.1–5.6, 6.1–6.8, 7.1–7.9, 12.5
"""
from __future__ import annotations

import asyncio
import io
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.main import app
from app.modules.auth_user_profile.auth.security import issue_token

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


# ── Module-level fixture — single DB shared by all tests ─────────────────────

_ENGINE = None
_SESSION_MAKER = None
_CLIENT_CNI = "PRF000001"
_CLIENT_EMAIL = "profile_client@example.com"
_CLIENT_PASSWORD = "Secure1234"
_CLIENT_TOKEN = None

_CLIENT2_CNI = "PRF000002"
_CLIENT2_EMAIL = "profile_other@example.com"


@pytest.fixture(scope="module", autouse=True)
def profile_db():
    global _ENGINE, _SESSION_MAKER, _CLIENT_TOKEN

    _ENGINE, _SESSION_MAKER = _make_engine_and_session()
    _run_sync(_create_tables(_ENGINE))

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

    # Seed users via the register endpoint
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.post(
            "/auth-catalogues/auth/register",
            json={
                "cni": _CLIENT_CNI,
                "nom": "Profile Client",
                "email": _CLIENT_EMAIL,
                "mot_de_passe": _CLIENT_PASSWORD,
                "role": "Client",
            },
        )
        assert r.status_code == 201, f"Fixture: failed to register client: {r.text}"

        r2 = c.post(
            "/auth-catalogues/auth/register",
            json={
                "cni": _CLIENT2_CNI,
                "nom": "Other Client",
                "email": _CLIENT2_EMAIL,
                "mot_de_passe": _CLIENT_PASSWORD,
                "role": "Client",
            },
        )
        assert r2.status_code == 201, f"Fixture: failed to register second client: {r2.text}"

    _CLIENT_TOKEN = issue_token(cni=_CLIENT_CNI, role="Client")

    yield

    app.dependency_overrides.clear()
    _run_sync(_ENGINE.dispose())


def _auth_headers(token: str | None = None) -> dict:
    return {"Authorization": f"Bearer {token or _CLIENT_TOKEN}"}


# ── GET /users/me ─────────────────────────────────────────────────────────────

def test_get_profile_returns_200():
    """
    Authenticated user can retrieve their own profile.
    Requirements: 6.1
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/auth-catalogues/users/me", headers=_auth_headers())
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["cni"] == _CLIENT_CNI
    assert body["email"] == _CLIENT_EMAIL
    assert body["role"] == "Client"
    assert "date_inscription" in body


# ── PATCH /users/me ───────────────────────────────────────────────────────────

def test_patch_profile_update_nom_returns_200():
    """
    PATCH with only a new nom succeeds and returns the updated profile.
    Requirements: 6.2
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.patch(
            "/auth-catalogues/users/me",
            headers=_auth_headers(),
            json={"nom": "Updated Name"},
        )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json()["nom"] == "Updated Name"


def test_patch_profile_update_email_returns_200():
    """
    PATCH with only a new email succeeds.
    Requirements: 6.2
    """
    new_email = "updated_profile@example.com"
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.patch(
            "/auth-catalogues/users/me",
            headers=_auth_headers(),
            json={"email": new_email},
        )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json()["email"] == new_email


def test_patch_profile_email_conflict_returns_409():
    """
    PATCH with an email already owned by another user returns 409.
    Requirements: 6.5
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.patch(
            "/auth-catalogues/users/me",
            headers=_auth_headers(),
            json={"email": _CLIENT2_EMAIL},
        )
    assert resp.status_code == 409, f"Expected 409, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", resp.json())
    assert detail.get("error") == "EMAIL_CONFLICT"


def test_patch_profile_nom_too_long_returns_422():
    """
    PATCH with nom > 100 characters returns 422.
    Requirements: 6.4
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.patch(
            "/auth-catalogues/users/me",
            headers=_auth_headers(),
            json={"nom": "A" * 101},
        )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


def test_patch_profile_empty_body_returns_422():
    """
    PATCH with an empty body (no updatable fields) returns 422.
    Requirements: 6.8
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.patch(
            "/auth-catalogues/users/me",
            headers=_auth_headers(),
            json={},
        )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", resp.json())
    assert detail.get("error") == "EMPTY_UPDATE"


def test_patch_profile_immutable_cni_returns_422():
    """
    PATCH with a cni field must return 422 IMMUTABLE_FIELD.
    Requirements: 6.6
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.patch(
            "/auth-catalogues/users/me",
            headers=_auth_headers(),
            json={"cni": "NEW123456"},
        )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", resp.json())
    assert detail.get("error") == "IMMUTABLE_FIELD"


def test_patch_profile_role_change_by_non_admin_returns_403():
    """
    A Client attempting to change their role via PATCH must get 403.
    Requirements: 6.7
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.patch(
            "/auth-catalogues/users/me",
            headers=_auth_headers(),
            json={"role": "Admin"},
        )
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", resp.json())
    assert detail.get("error") == "ROLE_CHANGE_FORBIDDEN"


# ── POST /users/me/photos ─────────────────────────────────────────────────────

_MOCK_URL = "https://storage.example.com/photos/PRF000001/test.jpg"


def _make_jpeg_file(size: int = 200) -> bytes:
    """Return a minimal JPEG-like byte string of the given size."""
    return b"\xff\xd8\xff" + b"x" * (size - 3)


def test_upload_photo_valid_returns_201():
    """
    Uploading a valid JPEG file with mocked storage returns 201 with photo fields.
    Requirements: 7.1
    """
    async def _mock_upload(cni: str, file: Any) -> str:
        return _MOCK_URL

    with patch(
        "app.modules.auth_user_profile.profile.service.SupabaseStorage.upload",
        new=_mock_upload,
    ):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post(
                "/auth-catalogues/users/me/photos",
                headers=_auth_headers(),
                files={"file": ("photo.jpg", io.BytesIO(_make_jpeg_file()), "image/jpeg")},
            )

    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "id_photo" in body
    assert "url_photo" in body
    assert "date_upload" in body


def test_upload_photo_wrong_mime_returns_422():
    """
    Uploading a PDF (wrong MIME type) returns 422 INVALID_MIME_TYPE.
    Requirements: 7.5
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/auth-catalogues/users/me/photos",
            headers=_auth_headers(),
            files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4 content"), "application/pdf")},
        )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", resp.json())
    assert detail.get("error") == "INVALID_MIME_TYPE"


def test_upload_photo_empty_file_returns_422():
    """
    Uploading a 0-byte file returns 422 EMPTY_FILE.
    Requirements: 7.6
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/auth-catalogues/users/me/photos",
            headers=_auth_headers(),
            files={"file": ("empty.jpg", io.BytesIO(b""), "image/jpeg")},
        )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", resp.json())
    assert detail.get("error") == "EMPTY_FILE"


def test_upload_photo_too_large_returns_413():
    """
    Uploading a file > 5 MB returns 413 FILE_TOO_LARGE.
    Requirements: 7.7
    """
    # 5 MB + 1 byte
    oversized = _make_jpeg_file(5_242_881)
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/auth-catalogues/users/me/photos",
            headers=_auth_headers(),
            files={"file": ("big.jpg", io.BytesIO(oversized), "image/jpeg")},
        )
    assert resp.status_code == 413, f"Expected 413, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", resp.json())
    assert detail.get("error") == "FILE_TOO_LARGE"


def test_upload_photo_storage_unavailable_returns_503():
    """
    When SupabaseStorage raises StorageUnavailableError the endpoint returns
    503 and no PhotoProfil record is created.
    Requirements: 7.8
    """
    from app.modules.auth_user_profile.profile.service import StorageUnavailableError


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



    async def _broken_upload(cni: str, file: Any) -> str:
        raise StorageUnavailableError("Storage is down.")

    with patch(
        "app.modules.auth_user_profile.profile.service.SupabaseStorage.upload",
        new=_broken_upload,
    ):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post(
                "/auth-catalogues/users/me/photos",
                headers=_auth_headers(),
                files={"file": ("photo.jpg", io.BytesIO(_make_jpeg_file()), "image/jpeg")},
            )

    assert resp.status_code == 503, f"Expected 503, got {resp.status_code}: {resp.text}"
    detail = resp.json().get("detail", resp.json())
    assert detail.get("error") == "STORAGE_UNAVAILABLE"

    # Verify no photo record was persisted
    async def _count_photos():
        async with _SESSION_MAKER() as session:
            # Count photos uploaded AFTER the seed photos (we look for url containing 'broken')
            result = await session.execute(
                text(
                    "SELECT COUNT(*) FROM photo_profil WHERE cni = :cni AND url_photo LIKE '%broken%'"
                ),
                {"cni": _CLIENT_CNI},
            )
            return result.scalar()

    broken_count = _run_sync(_count_photos())
    assert broken_count == 0, f"Expected 0 broken-storage photo records, got {broken_count}"


# ── GET /users/me/photos ──────────────────────────────────────────────────────

def test_get_photo_history_populated_returns_200():
    """
    After at least one successful upload, GET /users/me/photos returns 200
    with a non-empty list.
    Requirements: 7.9
    """
    # Ensure at least one upload succeeded earlier in this module's test run
    async def _mock_upload(cni: str, file: Any) -> str:
        return f"https://storage.example.com/photos/{cni}/hist.jpg"

    # Upload one photo first
    with patch(
        "app.modules.auth_user_profile.profile.service.SupabaseStorage.upload",
        new=_mock_upload,
    ):
        with TestClient(app, raise_server_exceptions=False) as c:
            c.post(
                "/auth-catalogues/users/me/photos",
                headers=_auth_headers(),
                files={"file": ("hist.jpg", io.BytesIO(_make_jpeg_file()), "image/jpeg")},
            )

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/auth-catalogues/users/me/photos", headers=_auth_headers())

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) > 0
    first = body[0]
    assert "id_photo" in first
    assert "url_photo" in first
    assert "date_upload" in first


def test_get_photo_history_empty_returns_200():
    """
    A new user with no photos gets 200 with an empty list.
    Requirements: 7.9
    """
    new_cni = "PRF000099"
    new_email = "newphoto@example.com"

    # Register the new user
    with TestClient(app, raise_server_exceptions=False) as c:
        reg = c.post(
            "/auth-catalogues/auth/register",
            json={
                "cni": new_cni,
                "nom": "New Photo User",
                "email": new_email,
                "mot_de_passe": "Secure1234",
                "role": "Client",
            },
        )
    assert reg.status_code == 201, f"Expected 201 registering new user: {reg.text}"

    token = issue_token(cni=new_cni, role="Client")
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get(
            "/auth-catalogues/users/me/photos",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json() == [], f"Expected empty list, got: {resp.json()}"


# ── GET /users/me/reports ─────────────────────────────────────────────────────

def test_get_report_history_empty_returns_200():
    """
    A user with no archived reports receives 200 with an empty list.
    Requirements: 12.5
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        # Use the new user registered above (no reports)
        new_cni = "PRF000098"
        new_email = "noreport@example.com"
        reg = c.post(
            "/auth-catalogues/auth/register",
            json={
                "cni": new_cni,
                "nom": "No Report User",
                "email": new_email,
                "mot_de_passe": "Secure1234",
                "role": "Client",
            },
        )
    assert reg.status_code == 201, f"Expected 201: {reg.text}"

    token = issue_token(cni=new_cni, role="Client")
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get(
            "/auth-catalogues/users/me/reports",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.json() == [], f"Expected empty list, got: {resp.json()}"
