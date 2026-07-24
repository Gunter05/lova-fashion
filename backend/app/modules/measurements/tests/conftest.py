"""
Test configuration for Module 2 — Photo Capture & Measurement Estimation.

Uses an in-memory SQLite database.  Supabase Storage and MediaPipe calls are
mocked so the tests run without any external connections.

cv2 / mediapipe are stubbed out via sys.modules so they don't need to be
installed in the test environment.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

# ── Stub absent heavy CV dependencies before any production imports ─────────
_absent_cv_mods = ("cv2", "mediapipe", "mediapipe.solutions", "mediapipe.solutions.pose")
_stub_targets = []
for _mod in _absent_cv_mods:
    try:
        __import__(_mod)
    except ImportError:
        _stub_targets.append(_mod)

for _mod in _stub_targets:
    sys.modules[_mod] = MagicMock()

# Stub estimation module if cv2/mediapipe are absent
if _stub_targets:
    _est_stub = MagicMock()
    _est_stub.BodyNotDetectedError = type("BodyNotDetectedError", (Exception,), {})
    _est_stub.LandmarkOccludedError = type("LandmarkOccludedError", (Exception,), {})
    _est_stub.EstimationTimeoutError = type("EstimationTimeoutError", (Exception,), {})
    sys.modules["app.modules.measurements.estimation"] = _est_stub
# ─────────────────────────────────────────────────────────────────────────

import asyncio
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.modules.measurements.dependencies import get_current_user, get_db
from app.modules.measurements.models import Base as MeasBase
from app.modules.measurements.router import router

# ---------------------------------------------------------------------------
# Shared test user
# ---------------------------------------------------------------------------

TEST_USER_ID = uuid.uuid4()

# ---------------------------------------------------------------------------
# In-memory SQLite engine
# ---------------------------------------------------------------------------

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def engine():
    eng = create_async_engine(
        SQLITE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with eng.begin() as conn:
        await conn.run_sync(MeasBase.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture(scope="session")
def session_factory(engine):
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture()
async def db_session(session_factory, engine):
    async with session_factory() as session:
        yield session
        await session.rollback()
        async with engine.begin() as conn:
            for table in reversed(MeasBase.metadata.sorted_tables):
                await conn.execute(text(f"DELETE FROM {table.name}"))


# ---------------------------------------------------------------------------
# Mock: SupabaseStorageAdapter
# ---------------------------------------------------------------------------

def make_mock_storage():
    """Return a mock storage adapter that records calls without hitting Supabase."""
    mock = MagicMock()
    mock.upload.return_value = "https://supabase.example.com/storage/v1/object/public/captures/test.jpg"
    mock.download.return_value = b""
    return mock


# ---------------------------------------------------------------------------
# FastAPI TestClient fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(db_session):
    """
    TestClient with:
    - SQLite in-memory DB via overridden get_db dependency
    - Fixed TEST_USER_ID via overridden get_current_user
    - SupabaseStorageAdapter replaced with a mock
    - MediaPipe / estimation patched to avoid CV processing
    """
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/measurements")

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return TEST_USER_ID

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    mock_storage = make_mock_storage()

    # Patch the storage singleton and MediaPipe body-detection used in upload_photo
    with (
        patch("app.modules.measurements.service._storage", mock_storage),
        patch("app.modules.measurements.service._estimator"),
        patch("app.modules.measurements.service._decode_image", return_value=None),
        patch("app.modules.measurements.service._run_pose", return_value=None),
        # Bypass MediaPipe body-presence check in upload_photo
        patch(
            "app.modules.measurements.service.CaptureSessionService.upload_photo",
            _mock_upload_photo,
        ),
    ):
        with TestClient(app, raise_server_exceptions=True) as tc:
            yield tc


# ---------------------------------------------------------------------------
# Simplified upload_photo replacement — skips Supabase & MediaPipe
# ---------------------------------------------------------------------------

async def _mock_upload_photo(self, session, user_id, view, file):
    """
    Minimal replacement for CaptureSessionService.upload_photo that:
    - Returns 422 for non JPEG/PNG content types (AC-02.2)
    - Returns 409 for completed sessions (AC-02.6)
    - Otherwise stores a fake URL and resets failed sessions
    """
    from fastapi import HTTPException

    if session.status == "success":
        raise HTTPException(status_code=409, detail="Session already completed.")

    content_type = file.content_type or ""
    if content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(status_code=422, detail="Format non supporté.")

    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="Fichier trop volumineux.")

    fake_url = f"https://supabase.example.com/storage/v1/object/public/captures/{view}.jpg"
    if view == "front":
        session.front_photo_url = fake_url
    else:
        session.profile_photo_url = fake_url

    if session.status == "failed":
        session.status = "empty"
        session.failure_reason = None
        session.retry_count = (session.retry_count or 0) + 1

    await self._db.commit()
    await self._db.refresh(session)
    return session
