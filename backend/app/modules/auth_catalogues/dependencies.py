"""
Role-guard dependencies for the Fabric Catalog (Module 3) and Pattern Catalog (Module 4).

This module does NOT validate JWTs. It only reads the `x-user-role` header
that Module 1 (Authentication) populates after validating the token upstream.

Module 3 exports:
    RoleType         — Literal type alias for the Module 3 roles (client, catalog_manager)
    get_current_role — FastAPI dependency; returns the validated role string (Module 3)
    require_role     — dependency factory; raises 403 if role doesn't match (Module 3)

Module 4 exports:
    require_client         — raises HTTP 403 if role != "client"
                             Implements: Req 1 AC4
    require_admin          — raises HTTP 403 if role != "administrator"
                             Implements: Req 4 AC8, Req 5 AC5, Req 6 AC6, Req 7 AC7, Req 8 AC7
    require_authenticated  — raises HTTP 401 if header is absent or role is unrecognised
                             Implements: Req 2 AC7, Req 3 AC6, Req 9 AC7
"""

from fastapi import Depends, HTTPException, Header
from typing import Literal, Optional

# ── Module 3 ──────────────────────────────────────────────────────────────────

# The two recognised role values for Module 3.
RoleType = Literal["client", "catalog_manager"]


async def get_current_role(x_user_role: Optional[str] = Header(None)) -> RoleType:
    """Read and validate the role claim from the request header (Module 3).

    The header `x-user-role` is expected to be set by the authentication
    middleware (Module 1) before the request reaches this module.

    Using ``Header(None)`` instead of ``Header(...)`` so that a missing header
    produces HTTP 403 (not FastAPI's default 422 Unprocessable Entity).

    Raises:
        HTTPException 403: if the header is missing or contains an
            unrecognised value.

    Returns:
        The validated role string ("client" or "catalog_manager").
    """
    if x_user_role is None or x_user_role not in ("client", "catalog_manager"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return x_user_role  # type: ignore[return-value]


def require_role(required: RoleType):
    """Return a FastAPI dependency that enforces a specific role (Module 3).

    Usage::

        @router.post("/categories", dependencies=[Depends(require_role("catalog_manager"))])

    Raises:
        HTTPException 403: if the caller's role does not match *required*.
    """
    async def check(role: RoleType = Depends(get_current_role)) -> RoleType:
        if role != required:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return role

    return check


# ── Module 4 ──────────────────────────────────────────────────────────────────

# All recognised roles across the full application.
_ALL_ROLES = ("client", "catalog_manager", "administrator")


async def require_client(x_user_role: Optional[str] = Header(None)) -> str:
    """FastAPI dependency that enforces the ``client`` role (Module 4).

    Reads the same `x-user-role` header set by Module 1.

    Implements: Req 1 AC4 — only users with the ``client`` role may call
    ``POST /models/init``.

    Raises:
        HTTPException 401: if the header is absent (unauthenticated).
        HTTPException 403: if the role is present but is not ``"client"``.

    Returns:
        The literal string ``"client"``.
    """
    if x_user_role is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if x_user_role != "client":
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return x_user_role


async def require_admin(x_user_role: Optional[str] = Header(None)) -> str:
    """FastAPI dependency that enforces the ``administrator`` role (Module 4).

    Reads the same `x-user-role` header set by Module 1.

    Implements:
        Req 4 AC8  — only administrators may edit Draft models.
        Req 5 AC5  — only administrators may assign fabrics.
        Req 6 AC6  — only administrators may publish models.
        Req 7 AC7  — only administrators may edit / republish Published models.
        Req 8 AC7  — only administrators may archive models.

    Note: The Module 4 admin role is ``"administrator"``, distinct from
    Module 3's ``"catalog_manager"``.

    Raises:
        HTTPException 401: if the header is absent (unauthenticated).
        HTTPException 403: if the role is present but is not ``"administrator"``.

    Returns:
        The literal string ``"administrator"``.
    """
    if x_user_role is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if x_user_role != "administrator":
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return x_user_role


async def require_authenticated(x_user_role: Optional[str] = Header(None)) -> str:
    """FastAPI dependency that accepts any recognised role (Module 4).

    Reads the same `x-user-role` header set by Module 1. Any of the three
    application roles (``client``, ``catalog_manager``, ``administrator``)
    is accepted. A missing or unrecognised header raises HTTP 401 because
    the request is effectively unauthenticated.

    Implements:
        Req 2 AC7  — unauthenticated requests to ``GET /models`` → 401.
        Req 3 AC6  — unauthenticated requests to ``GET /models/{id}`` → 401.
        Req 9 AC7  — unauthenticated requests to ``GET /models/{id}/constraints`` → 401.

    Raises:
        HTTPException 401: if the header is absent or contains an
            unrecognised role value.

    Returns:
        The validated role string (one of ``"client"``, ``"catalog_manager"``,
        or ``"administrator"``).
    """
    if x_user_role is None or x_user_role not in _ALL_ROLES:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return x_user_role
