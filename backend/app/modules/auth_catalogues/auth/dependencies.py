"""
FastAPI reusable dependencies for authentication and authorisation.

Provides:
  - get_current_user: extracts Bearer token, validates JWT, checks denylist,
                      returns UserClaims(cni, role)
  - require_role: factory for role-based access control dependencies

Design reference: Key Dependency Interfaces, Token Validation Flow
Requirements: 4.1–4.6, 5.6
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth_catalogues.auth.repository import UserRepository
from app.modules.auth_catalogues.auth.security import (
    decode_token,
    TokenExpiredError,
    TokenInvalidError,
)

# ── OAuth2 scheme — extracts Bearer token from Authorization header ────────────
# auto_error=False so we can return our own envelope instead of FastAPI's default
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


@dataclass(frozen=True)
class UserClaims:
    """Decoded JWT claims injected into request handlers (Req 4.6)."""

    cni: str
    role: str


def _error_response(
    http_status: int,
    error_code: str,
    message: str,
    headers: dict | None = None,
) -> HTTPException:
    """Build an HTTPException whose detail matches the error-envelope schema.

    The envelope shape is:
        {"error": "<SCREAMING_SNAKE_CASE>", "field": null, "message": "<human text>"}
    """
    detail = {"error": error_code, "field": None, "message": message}
    kwargs: dict = {"status_code": http_status, "detail": detail}
    if headers:
        kwargs["headers"] = headers
    return HTTPException(**kwargs)


# ── Primary dependency ─────────────────────────────────────────────────────────

async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> UserClaims:
    """
    FastAPI dependency — validates the Bearer JWT, checks the token denylist,
    and returns :class:`UserClaims` for the authenticated user.

    Token Validation Flow (design.md):
      1. Extract token from "Authorization: Bearer <token>" header.
      2. Decode JWT, verify HS256 signature + iss claim (security.decode_token).
      3. Confirm required claims present: cni, role, exp, jti.
      4. Confirm exp > NOW() (decode_token raises TokenExpiredError otherwise).
      5. Confirm jti NOT IN token_denylist.
      6. Return UserClaims(cni, role).

    Raises:
        HTTPException 401 – missing / expired / invalid / denied token.
    """
    _bearer_headers = {"WWW-Authenticate": "Bearer"}

    # Step 1: Require a token — oauth2_scheme returns None when header absent
    if not token:
        raise _error_response(
            status.HTTP_401_UNAUTHORIZED,
            "TOKEN_MISSING",
            "Authentication credentials are required.",
            _bearer_headers,
        )

    # Steps 2–4: Decode and verify JWT (signature, iss, required claims, expiry)
    try:
        payload = decode_token(token)
    except TokenExpiredError:
        raise _error_response(
            status.HTTP_401_UNAUTHORIZED,
            "TOKEN_EXPIRED",
            "Token has expired.",
            _bearer_headers,
        )
    except TokenInvalidError:
        raise _error_response(
            status.HTTP_401_UNAUTHORIZED,
            "TOKEN_INVALID",
            "Token is invalid.",
            _bearer_headers,
        )

    # Step 5: Check token denylist via repository
    jti: str | None = payload.get("jti")
    repo = UserRepository(db)
    if jti and await repo.is_jti_denied(jti):
        raise _error_response(
            status.HTTP_401_UNAUTHORIZED,
            "TOKEN_DENIED",
            "Token has been invalidated.",
            _bearer_headers,
        )

    # Step 6: Return claims
    cni: str = payload.get("cni", "")
    role: str = payload.get("role", "")
    return UserClaims(cni=cni, role=role)


# ── RBAC factory ───────────────────────────────────────────────────────────────

def require_role(*roles: str) -> Callable:
    """
    Factory that returns a FastAPI dependency enforcing role membership.

    Usage::

        @router.get("/admin/users", dependencies=[Depends(require_role("Admin"))])
        async def list_users(): ...

        @router.get("/data", dependencies=[Depends(require_role("Tailor", "Admin"))])
        async def get_data(): ...

    Args:
        *roles: One or more role strings (``"Client"``, ``"Tailor"``, ``"Admin"``).

    Returns:
        A dependency callable that yields the authenticated :class:`UserClaims`
        when the role check passes.

    Raises:
        HTTPException 403 – if the current user's role is not in *roles*.
    """

    async def role_checker(
        current_user: UserClaims = Depends(get_current_user),
    ) -> UserClaims:
        """Inner dependency: validates role membership and propagates UserClaims."""
        if current_user.role not in roles:
            raise _error_response(
                status.HTTP_403_FORBIDDEN,
                "FORBIDDEN",
                f"Access denied. Required role: {', '.join(roles)}.",
            )
        return current_user

    return role_checker
