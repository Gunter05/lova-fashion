"""
Property-based tests — Property 2: CNI and Email Uniqueness Cardinality Invariant.

Feature: auth-user-profile
Property 2: CNI and Email Uniqueness — Cardinality Invariant
Validates: Requirements 1.2, 1.3, 6.5

Pattern: Invariant — cardinality of users per CNI = 1, cardinality of users per email = 1

For any set of registration attempts containing a duplicate CNI or email value,
the total number of User records sharing that CNI or email shall always equal
exactly 1 after any number of attempts.  All subsequent attempts after the first
must be rejected with HTTP 409.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine, event as sa_event, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.models import Base
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



# SQLite does not understand the PG regex operator inside CHECK constraints.
# We create tables without them by removing the __table_args__ CHECK on `users`.
# The simplest approach: use `checkfirst=True` on create_all and strip unsupported
# constraints by patching the event listener.

SQLITE_URL = "sqlite+aiosqlite:///:memory:"


def _make_engine_and_session():
    """Return a fresh (engine, sessionmaker) pair backed by an in-memory SQLite DB."""
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


def _build_client_with_db(engine, session_maker):
    """Build a FastAPI TestClient with get_db overridden to use the given session_maker."""

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


async def _create_tables(engine):
    """
    Create all ORM tables for SQLite, stripping PostgreSQL-specific constructs.

    The `users` table has a CHECK constraint using `~` (regex match), which is
    a PostgreSQL-only operator.  We create the table manually via raw SQL that
    SQLite understands, then create the remaining tables via metadata.create_all.
    """
    async with engine.begin() as conn:
        # Create users table manually (SQLite-compatible)
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
        # Create token_denylist table manually
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS token_denylist (
                jti         TEXT     NOT NULL PRIMARY KEY,
                expires_at  DATETIME NOT NULL
            )
        """))
        # Create other tables that don't have PG-only constraints
        # photo_profil, mensuration, rapport_archive, tailor_client_assignment
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS photo_profil (
                id_photo    VARCHAR(36)  NOT NULL PRIMARY KEY,
                cni         VARCHAR(9)   NOT NULL REFERENCES users(cni) ON DELETE CASCADE,
                url_photo   TEXT         NOT NULL,
                date_upload DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS mensuration (
                id_mesure           VARCHAR(36)  NOT NULL PRIMARY KEY,
                cni                 VARCHAR(9)   NOT NULL REFERENCES users(cni) ON DELETE CASCADE,
                tour_poitrine       NUMERIC(6,2) NOT NULL,
                tour_taille         NUMERIC(6,2) NOT NULL,
                tour_hanches        NUMERIC(6,2) NOT NULL,
                longueur_bras       NUMERIC(6,2) NOT NULL,
                hauteur             NUMERIC(6,2) NOT NULL,
                date_mensuration    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                source_event_hash   TEXT         UNIQUE
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS rapport_archive (
                id               VARCHAR(36)  NOT NULL PRIMARY KEY,
                cni              VARCHAR(9)   NOT NULL REFERENCES users(cni) ON DELETE CASCADE,
                report_id        TEXT         NOT NULL,
                date_generation  DATETIME     NOT NULL,
                archived_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (cni, report_id)
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tailor_client_assignment (
                tailor_cni  VARCHAR(9)  NOT NULL REFERENCES users(cni) ON DELETE CASCADE,
                client_cni  VARCHAR(9)  NOT NULL REFERENCES users(cni) ON DELETE CASCADE,
                assigned_at DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (tailor_cni, client_cni)
            )
        """))


# ── Strategies ────────────────────────────────────────────────────────────────

# CNI: exactly 9 alphanumeric characters (matching the schema regex)
cni_strategy = st.from_regex(r"[A-Za-z0-9]{9}", fullmatch=True)

# Attempt count: 2–5 registration attempts with the same CNI or email
attempt_count_strategy = st.integers(min_value=2, max_value=5)

# A minimal valid nom
nom_strategy = st.just("Test User")

# A valid password
password_strategy = st.just("Passw0rd!")

# A valid role
role_strategy = st.just("Client")


def _unique_email(suffix: str) -> str:
    """Generate an email that passes Pydantic's EmailStr validation."""
    safe = "".join(c if c.isalnum() else "a" for c in suffix)
    return f"user{safe[:8]}@example.com"


# ── Property 2a: CNI uniqueness — exactly 1 record after N attempts ────────────

@given(
    cni=cni_strategy,
    attempt_count=attempt_count_strategy,
)
@settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    deadline=10_000,
)
def test_cni_uniqueness_cardinality_invariant(cni: str, attempt_count: int):
    """
    Feature: auth-user-profile, Property 2: CNI and Email Uniqueness — Cardinality Invariant

    After N registration attempts with the same CNI, exactly 1 User record exists
    and all attempts after the first are rejected with HTTP 409.

    Validates: Requirements 1.2
    """
    engine, session_maker = _make_engine_and_session()

    # Create tables synchronously within the test
    _run_sync(_create_tables(engine))

    client = _build_client_with_db(engine, session_maker)

    base_email = f"cni{cni.lower()[:6]}"
    success_count = 0
    conflict_count = 0

    for i in range(attempt_count):
        # Each attempt uses the SAME CNI but a DIFFERENT email to isolate the CNI constraint
        payload = {
            "cni": cni,
            "nom": "Test User",
            "email": f"user{i}{base_email}@example.com",
            "mot_de_passe": "Passw0rd!",
            "role": "Client",
        }
        response = client.post("/auth-catalogues/auth/register", json=payload)
        if response.status_code == 201:
            success_count += 1
        elif response.status_code == 409:
            conflict_count += 1
            body = response.json()
            # FastAPI wraps HTTPException detail in {"detail": {...}}
            detail = body.get("detail", body)
            assert detail.get("error") == "DUPLICATE_RESOURCE", (
                f"Expected error=DUPLICATE_RESOURCE, got {body}"
            )
            assert detail.get("field") == "cni", (
                f"Expected field=cni for CNI conflict, got {detail.get('field')}"
            )
        else:
            # 422 validation failures are unexpected here — fail loudly
            assert False, (
                f"Unexpected status {response.status_code} on attempt {i}: {response.text}"
            )

    # Invariant: exactly 1 success regardless of how many attempts were made
    assert success_count == 1, (
        f"Expected exactly 1 successful registration for CNI={cni}, "
        f"got success_count={success_count}"
    )
    assert conflict_count == attempt_count - 1, (
        f"Expected {attempt_count - 1} conflict rejections, got {conflict_count}"
    )

    # Clean up
    app.dependency_overrides.clear()
    _run_sync(engine.dispose())


# ── Property 2b: Email uniqueness — exactly 1 record after N attempts ──────────

@given(
    cni_base=cni_strategy,
    attempt_count=attempt_count_strategy,
)
@settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    deadline=10_000,
)
def test_email_uniqueness_cardinality_invariant(cni_base: str, attempt_count: int):
    """
    Feature: auth-user-profile, Property 2: CNI and Email Uniqueness — Cardinality Invariant

    After N registration attempts with the same email, exactly 1 User record exists
    and all attempts after the first are rejected with HTTP 409.

    Validates: Requirements 1.3, 6.5
    """
    engine, session_maker = _make_engine_and_session()
    _run_sync(_create_tables(engine))
    client = _build_client_with_db(engine, session_maker)

    shared_email = f"shared{cni_base.lower()[:6]}@example.com"
    success_count = 0
    conflict_count = 0

    for i in range(attempt_count):
        # Each attempt uses the SAME email but a DIFFERENT (valid) CNI to isolate the
        # email constraint. We construct unique CNIs by overwriting the last digit.
        suffix = str(i % 10)
        unique_cni = cni_base[:8] + suffix

        payload = {
            "cni": unique_cni,
            "nom": "Test User",
            "email": shared_email,
            "mot_de_passe": "Passw0rd!",
            "role": "Client",
        }
        response = client.post("/auth-catalogues/auth/register", json=payload)
        if response.status_code == 201:
            success_count += 1
        elif response.status_code == 409:
            conflict_count += 1
            body = response.json()
            # FastAPI wraps HTTPException detail in {"detail": {...}}
            detail = body.get("detail", body)
            assert detail.get("error") == "DUPLICATE_RESOURCE", (
                f"Expected error=DUPLICATE_RESOURCE, got {body}"
            )
            assert detail.get("field") == "email", (
                f"Expected field=email for email conflict, got {detail.get('field')}"
            )
        else:
            assert False, (
                f"Unexpected status {response.status_code} on attempt {i}: {response.text}"
            )

    assert success_count == 1, (
        f"Expected exactly 1 successful registration for email={shared_email}, "
        f"got success_count={success_count}"
    )
    assert conflict_count == attempt_count - 1, (
        f"Expected {attempt_count - 1} conflict rejections, got {conflict_count}"
    )

    app.dependency_overrides.clear()
    _run_sync(engine.dispose())
