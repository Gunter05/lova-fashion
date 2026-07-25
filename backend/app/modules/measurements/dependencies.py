"""
FastAPI dependency injectors for Module 2 — Photo Capture & Measurement Estimation.
Tasks T-08.1, T-08.2 — AC-01.1, AC-02.6, NFR-03, Design §5

Three dependencies consumed by every router endpoint:

    get_db()               → AsyncSession   (request-scoped DB session)
    get_current_user()     → uuid.UUID      (authenticated user_id from JWT)
    get_session_or_404()   → CaptureSession (session owned by caller, or 403/404)
"""

from __future__ import annotations

import os
import uuid
from typing import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.measurements.models import CaptureSession
from app.db.session import AsyncSessionLocal as AsyncSessionFactory

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Supabase signs its JWTs with the project JWT secret.
# Set SUPABASE_JWT_SECRET in .env (copy from Supabase dashboard →
# Project Settings → API → JWT Secret).
_JWT_SECRET: str = os.environ.get("SUPABASE_JWT_SECRET", "")
_JWT_ALGORITHM: str = "HS256"

# FastAPI HTTP Bearer scheme — extracts the Bearer token from the
# Authorization header automatically.
_bearer_scheme = HTTPBearer(auto_error=True)


# ---------------------------------------------------------------------------
# T-08.3 — get_db: request-scoped async session
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a SQLAlchemy AsyncSession for the duration of one HTTP request.
    The session is committed or rolled back automatically on exit.
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# T-08.1 — get_current_user: decode JWT → user_id UUID
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> uuid.UUID:
    """
    Decode a Supabase-issued Bearer JWT and return the caller's user_id.

    Supabase embeds the user UUID in the 'sub' claim of every access token.

    Raises
    ------
    HTTPException 401 — Token missing, malformed, expired, or signature invalid.
                        (AC-01.1, NFR-03)
    """
    token = credentials.credentials

    if not _JWT_SECRET:
        # Fail loudly at runtime if the secret was not configured
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "SUPABASE_JWT_SECRET n'est pas configuré. "
                "Contactez l'administrateur."
            ),
        )

    try:
        payload = jwt.decode(
            token,
            _JWT_SECRET,
            algorithms=[_JWT_ALGORITHM],
            # Supabase sets audience to "authenticated" for user tokens
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
# T-08.2 — get_session_or_404: load session + verify ownership
# ---------------------------------------------------------------------------

async def get_session_or_404(
    session_id: uuid.UUID,
    current_user: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CaptureSession:
    """
    Load a CaptureSession by primary key and assert the caller owns it.

    Returns
    -------
    CaptureSession — the loaded and verified session row.

    Raises
    ------
    HTTPException 404 — session_id does not exist.
    HTTPException 403 — session exists but belongs to a different user.
                        (AC-02.6)
    """
    session: CaptureSession | None = await db.get(CaptureSession, session_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} introuvable.",
        )

    if session.user_id != current_user:
        # Return 403, not 404, to confirm that a resource exists but is
        # forbidden — consistent with REST best practices for owned resources.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous n'êtes pas autorisé à accéder à cette session.",
        )

    return session
