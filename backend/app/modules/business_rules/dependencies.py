"""
FastAPI dependency injectors for Module 5 — Ease Allowance Calculation Engine.
Tasks T-05.1, T-05.2, T-05.3 — AC-01.1, AC-05.2, NFR-02, Design §5

Three dependencies consumed by every router endpoint:

    get_db()                → AsyncSession          (request-scoped DB session)
    get_current_user()      → uuid.UUID             (authenticated user_id from JWT)
    get_adjustment_or_404() → MeasurementAdjustment (loaded by PK, or 404)

Reuses the same JWT decode pattern established in measurements/dependencies.py,
reading SUPABASE_JWT_SECRET and SUPABASE_JWT_ALGORITHM from the environment.
The async DB session factory is also shared from measurements/service.py to
guarantee all modules use the same SQLAlchemy engine and connection pool.
"""

from __future__ import annotations

import os
import uuid
from typing import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.business_rules.models import MeasurementAdjustment
# Reuse the shared async session factory from Module 2 to keep one engine
from app.modules.measurements.service import AsyncSessionFactory

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_JWT_SECRET: str = os.environ.get("SUPABASE_JWT_SECRET", "")
_JWT_ALGORITHM: str = "HS256"

_bearer_scheme = HTTPBearer(auto_error=True)


# ---------------------------------------------------------------------------
# T-05.2 — get_db: request-scoped async session
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a SQLAlchemy AsyncSession for the duration of one HTTP request.
    Auto-commits on clean exit, rolls back on exception.
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# T-05.1 — get_current_user: decode JWT → user_id UUID
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> uuid.UUID:
    """
    Decode a Supabase Bearer JWT and return the caller's user_id UUID.

    Raises
    ------
    HTTPException 500 — SUPABASE_JWT_SECRET not configured.
    HTTPException 401 — token missing, malformed, expired, or invalid signature.
    AC-01.1, NFR-02
    """
    if not _JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "SUPABASE_JWT_SECRET n'est pas configuré. "
                "Contactez l'administrateur."
            ),
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            _JWT_SECRET,
            algorithms=[_JWT_ALGORITHM],
            options={"verify_aud": False},
        )
        sub: str | None = payload.get("sub")
        if sub is None:
            raise JWTError("Claim 'sub' absent du token.")
        return uuid.UUID(sub)

    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token d'authentification invalide ou expiré.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# T-05.3 — get_adjustment_or_404: load MeasurementAdjustment by PK
# ---------------------------------------------------------------------------

async def get_adjustment_or_404(
    adjustment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> MeasurementAdjustment:
    """
    Load a MeasurementAdjustment by primary key.
    Ownership verification is deferred to EaseCalculationService.get_adjustment()
    because it requires a session join that the service already performs.

    Raises
    ------
    HTTPException 404 — adjustment_id does not exist.
    AC-05.2 · Design §5.2
    """
    adjustment: MeasurementAdjustment | None = await db.get(
        MeasurementAdjustment, adjustment_id
    )

    if adjustment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ajustement {adjustment_id} introuvable.",
        )

    return adjustment


# ---------------------------------------------------------------------------
# T-07.1 — require_admin: decode JWT → check is_admin claim → return user_id
# ---------------------------------------------------------------------------

async def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> uuid.UUID:
    """
    Decode a Supabase Bearer JWT, verify the ``is_admin`` claim, and return
    the caller's user_id UUID.

    The ``is_admin`` claim must be present and truthy in the JWT payload.
    If the claim is absent or ``false``, the request is rejected with HTTP 403.
    The 403 response body intentionally contains no rule content (no ``rule_id``,
    ``mathematical_condition``, ``severity_level``, or ``explanation_message``).

    Raises
    ------
    HTTPException 500 — SUPABASE_JWT_SECRET not configured.
    HTTPException 401 — token missing, malformed, expired, or invalid signature.
    HTTPException 403 — ``is_admin`` claim is absent or false.

    Returns
    -------
    uuid.UUID — the authenticated admin's user_id.

    Implements: Requirements 9.5, 13.1
    """
    if not _JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "SUPABASE_JWT_SECRET n'est pas configuré. "
                "Contactez l'administrateur."
            ),
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            _JWT_SECRET,
            algorithms=[_JWT_ALGORITHM],
            options={"verify_aud": False},
        )
        sub: str | None = payload.get("sub")
        if sub is None:
            raise JWTError("Claim 'sub' absent du token.")
        user_id = uuid.UUID(sub)

    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token d'authentification invalide ou expiré.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not payload.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return user_id
