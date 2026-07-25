"""
Property-based tests — Property 6: Profile Photo History — Append-Only Invariant.

Feature: auth-user-profile
Property 6: Profile Photo History — Append-Only Invariant
Validates: Requirements 7.4, 7.1

Pattern: Invariant — append-only collection, no destructive updates to prior entries

For any User who has uploaded k profile pictures, uploading a new valid picture shall
result in exactly k+1 photo_profil records for that User, and all pre-existing records
shall be unmodified (same url_photo and date_upload values as before the upload).

Note: Supabase Storage upload is mocked to return a deterministic URL of the form
      https://storage.example.com/photos/{cni}/{uuid}.jpg
      so the test runs without any network calls.
"""
from __future__ import annotations

import asyncio
import io
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.modules.auth_catalogues.profile.service import (
    ProfileService,
    StorageUnavailableError,
    SupabaseStorage,
)

# ── SQLite in-memory helpers ──────────────────────────────────────────────────

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


def _make_engine_and_session():
    """Return a fresh (engine, async_sessionmaker) backed by an in-memory SQLite DB."""
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
    """Create minimal SQLite-compatible tables needed for the photo tests."""
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
            CREATE TABLE IF NOT EXISTS photo_profil (
                id_photo    VARCHAR(36) NOT NULL PRIMARY KEY,
                cni         VARCHAR(9)  NOT NULL REFERENCES users(cni) ON DELETE CASCADE,
                url_photo   TEXT        NOT NULL,
                date_upload DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))


async def _seed_user(session: AsyncSession, cni: str) -> None:
    """Insert a minimal user row so FK constraints are satisfied.

    Note: SAEnum(UserRole, ...) stores enum *names* (e.g. 'CLIENT'), not values
    ('Client').  We must use the name here so that ORM lookups succeed.
    """
    await session.execute(text("""
        INSERT OR IGNORE INTO users (cni, nom, email, mot_de_passe, role, is_active)
        VALUES (:cni, :nom, :email, :pwd, :role, 1)
    """), {
        "cni": cni,
        "nom": "Test User",
        "email": f"{cni.lower()}@example.com",
        "pwd": "hashed",
        "role": "CLIENT",  # SAEnum stores enum *name*, not value
    })
    await session.flush()


async def _seed_photos(session: AsyncSession, cni: str, k: int) -> list[dict]:
    """
    Seed k photo records for *cni*.
    Returns a list of dicts with {'id_photo', 'url_photo', 'date_upload'} for
    easy comparison after the upload.
    """
    seeded: list[dict] = []
    for i in range(k):
        photo_id = str(uuid.uuid4())
        url = f"https://storage.example.com/photos/{cni}/seed-{i}.jpg"
        now = datetime.now(timezone.utc).isoformat()
        await session.execute(text("""
            INSERT INTO photo_profil (id_photo, cni, url_photo, date_upload)
            VALUES (:id_photo, :cni, :url_photo, :date_upload)
        """), {"id_photo": photo_id, "cni": cni, "url_photo": url, "date_upload": now})
        seeded.append({"id_photo": photo_id, "url_photo": url, "date_upload": now})
    await session.flush()
    return seeded


# ── Mock UploadFile ───────────────────────────────────────────────────────────

class _FakeUploadFile:
    """
    Minimal UploadFile-compatible stub that carries a small valid JPEG body.
    """

    def __init__(self, cni: str, content: bytes = b"\xff\xd8\xff" + b"x" * 100):
        self.filename = f"photo_{cni}.jpg"
        self.content_type = "image/jpeg"
        self._content = content
        self.size = len(content)
        self._pos = 0

    async def read(self, size: int = -1) -> bytes:
        if size == -1:
            data = self._content[self._pos:]
            self._pos = len(self._content)
        else:
            data = self._content[self._pos: self._pos + size]
            self._pos += len(data)
        return data

    async def seek(self, offset: int) -> None:
        self._pos = offset


# ── Mock SupabaseStorage ───────────────────────────────────────────────────────

class _MockStorage:
    """
    Deterministic storage mock.
    Returns https://storage.example.com/photos/{cni}/{uuid}.jpg.
    Does NOT touch the network.
    """

    @staticmethod
    async def upload(cni: str, file: Any) -> str:
        return f"https://storage.example.com/photos/{cni}/{uuid.uuid4()}.jpg"


# ── Property 6 — Append-Only Invariant ───────────────────────────────────────

@given(k=st.integers(min_value=0, max_value=10))
@settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    deadline=10_000,
)
def test_photo_history_append_only_invariant(k: int):
    """
    Feature: auth-user-profile, Property 6: Profile Photo History — Append-Only Invariant

    Seed k photos in the DB, upload one more via ProfileService.upload_photo, then
    assert that:
      1. Exactly k+1 photo_profil records exist for the user.
      2. All k pre-existing records have unchanged url_photo and date_upload.

    Validates: Requirements 7.4, 7.1
    """
    _run_sync(
        _run_append_only_test(k)
    )


async def _query_photos_raw(session: AsyncSession, cni: str) -> dict[str, dict]:
    """
    Return all photo_profil rows for *cni* as a plain dict keyed by id_photo.
    Uses raw SQL to avoid SQLAlchemy Enum processing issues on SQLite
    (SQLite stores 'Client' but the SAEnum type expects 'CLIENT').
    """
    result = await session.execute(
        text("SELECT id_photo, url_photo, date_upload FROM photo_profil WHERE cni = :cni"),
        {"cni": cni},
    )
    return {
        row.id_photo: {"url_photo": row.url_photo, "date_upload": row.date_upload}
        for row in result.fetchall()
    }


async def _run_append_only_test(k: int) -> None:
    # Fresh isolated DB per hypothesis example
    cni = "TST123456"
    engine, session_maker = _make_engine_and_session()
    await _create_tables(engine)

    async with session_maker() as session:
        # 1. Seed user (raw SQL — avoids SAEnum lookup)
        await _seed_user(session, cni)
        await session.commit()

        # 2. Seed k existing photos
        await _seed_photos(session, cni, k)
        await session.commit()

        # 3. Capture the pre-upload state using raw SQL
        before_records = await _query_photos_raw(session, cni)
        assert len(before_records) == k, (
            f"Expected {k} records before upload, found {len(before_records)}"
        )

        # 4. Perform the upload via ProfileService (using _MockStorage)
        service = ProfileService(session)
        fake_file = _FakeUploadFile(cni)
        response = await service.upload_photo(cni, fake_file, storage=_MockStorage)

        await session.commit()

        # 5. Re-query the DB for the post-upload state (raw SQL)
        after_records = await _query_photos_raw(session, cni)

        # Invariant A: exactly k+1 records exist
        assert len(after_records) == k + 1, (
            f"Expected {k + 1} records after upload, found {len(after_records)}"
        )

        # Invariant B: all k pre-existing records are unmodified
        for photo_id, original in before_records.items():
            assert photo_id in after_records, (
                f"Pre-existing photo {photo_id} is missing after upload!"
            )
            current = after_records[photo_id]

            # url_photo must be unchanged
            assert current["url_photo"] == original["url_photo"], (
                f"url_photo changed for photo {photo_id}: "
                f"was '{original['url_photo']}', now '{current['url_photo']}'"
            )

            # date_upload must be unchanged (compare as strings to avoid tz issues)
            assert str(current["date_upload"]) == str(original["date_upload"]), (
                f"date_upload changed for photo {photo_id}: "
                f"was {original['date_upload']}, now {current['date_upload']}"
            )

        # Invariant C: the new record has the URL returned by the service
        new_photo_ids = set(after_records.keys()) - set(before_records.keys())
        assert len(new_photo_ids) == 1, (
            f"Expected exactly 1 new photo record, found {len(new_photo_ids)}"
        )
        new_id = next(iter(new_photo_ids))
        assert after_records[new_id]["url_photo"] == response.url_photo, (
            f"New record url_photo '{after_records[new_id]['url_photo']}' "
            f"does not match service response url_photo '{response.url_photo}'"
        )

    await engine.dispose()


# ── Example-based sanity checks ───────────────────────────────────────────────

def test_upload_wrong_mime_type_raises_422():
    """MIME type validation: non-image file raises HTTP 422 INVALID_MIME_TYPE."""
    from fastapi import HTTPException

    async def _run():
        engine, session_maker = _make_engine_and_session()
        await _create_tables(engine)
        async with session_maker() as session:
            cni = "TST999001"
            await _seed_user(session, cni)
            await session.commit()

            service = ProfileService(session)
            fake_file = _FakeUploadFile(cni)
            fake_file.content_type = "application/pdf"  # wrong MIME

            with pytest.raises(HTTPException) as exc_info:
                await service.upload_photo(cni, fake_file, storage=_MockStorage)

            assert exc_info.value.status_code == 422
            assert exc_info.value.detail["error"] == "INVALID_MIME_TYPE"

        await engine.dispose()

    _run_sync(_run())


def test_upload_empty_file_raises_422():
    """Empty file raises HTTP 422 EMPTY_FILE."""
    from fastapi import HTTPException

    async def _run():
        engine, session_maker = _make_engine_and_session()
        await _create_tables(engine)
        async with session_maker() as session:
            cni = "TST999002"
            await _seed_user(session, cni)
            await session.commit()

            service = ProfileService(session)
            fake_file = _FakeUploadFile(cni, content=b"")  # 0 bytes

            with pytest.raises(HTTPException) as exc_info:
                await service.upload_photo(cni, fake_file, storage=_MockStorage)

            assert exc_info.value.status_code == 422
            assert exc_info.value.detail["error"] == "EMPTY_FILE"

        await engine.dispose()

    _run_sync(_run())


def test_upload_too_large_raises_413():
    """File exceeding 5 MB raises HTTP 413 FILE_TOO_LARGE."""
    from fastapi import HTTPException

    async def _run():
        engine, session_maker = _make_engine_and_session()
        await _create_tables(engine)
        async with session_maker() as session:
            cni = "TST999003"
            await _seed_user(session, cni)
            await session.commit()

            service = ProfileService(session)
            # 5 MB + 1 byte
            oversized_content = b"\xff\xd8\xff" + b"x" * (5_242_880 - 2)
            fake_file = _FakeUploadFile(cni, content=oversized_content)

            with pytest.raises(HTTPException) as exc_info:
                await service.upload_photo(cni, fake_file, storage=_MockStorage)

            assert exc_info.value.status_code == 413
            assert exc_info.value.detail["error"] == "FILE_TOO_LARGE"

        await engine.dispose()

    _run_sync(_run())


def test_upload_storage_unavailable_raises_503():
    """StorageUnavailableError from the storage backend raises HTTP 503."""
    from fastapi import HTTPException


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



    class _BrokenStorage:
        @staticmethod
        async def upload(cni: str, file: Any) -> str:
            raise StorageUnavailableError("Storage is down.")

    async def _run():
        engine, session_maker = _make_engine_and_session()
        await _create_tables(engine)
        async with session_maker() as session:
            cni = "TST999004"
            await _seed_user(session, cni)
            await session.commit()

            service = ProfileService(session)
            fake_file = _FakeUploadFile(cni)

            with pytest.raises(HTTPException) as exc_info:
                await service.upload_photo(cni, fake_file, storage=_BrokenStorage)

            assert exc_info.value.status_code == 503
            assert exc_info.value.detail["error"] == "STORAGE_UNAVAILABLE"

        await engine.dispose()

    _run_sync(_run())
