"""
Role-guard dependency for the Fabric Catalog module.

This module does NOT validate JWTs. It only reads the `x-user-role` header
that Module 1 (Authentication) populates after validating the token upstream.

Exports:
    RoleType         — Literal type alias for the two valid roles
    get_current_role — FastAPI dependency; returns the validated role string
    require_role     — dependency factory; raises 403 if role doesn't match
"""

from fastapi import Depends, HTTPException, Header
from typing import Literal, Optional

# The two recognised role values in this application.
RoleType = Literal["client", "catalog_manager"]


async def get_current_role(x_user_role: Optional[str] = Header(None)) -> RoleType:
    """Read and validate the role claim from the request header.

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
    """Return a FastAPI dependency that enforces a specific role.

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
