"""
Profile and Admin HTTP router for Module 1.

Mounts all /users/me/* endpoints (any authenticated role) and
all /admin/users/* endpoints (Admin role only).

Design reference: API Endpoints — Profile Endpoints, Admin Endpoints
Requirements: 5.1–5.6, 6.1–6.8, 7.1–7.9, 13.1–13.7
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth_catalogues.auth.dependencies import (
    UserClaims,
    get_current_user,
    require_role,
)
from app.modules.auth_catalogues.profile.schemas import (
    AdminUserResponse,
    PhotoProfilResponse,
    RapportArchiveResponse,
    RoleUpdateRequest,
    UpdateProfileRequest,
    UserProfileResponse,
)
from app.modules.auth_catalogues.profile.service import ProfileService

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _service(db: AsyncSession) -> ProfileService:
    """Instantiate ProfileService with the current DB session."""
    return ProfileService(db)


# ── Profile endpoints (any authenticated role) ────────────────────────────────

@router.get(
    "/users/me",
    response_model=UserProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get authenticated user's profile",
)
async def get_my_profile(
    current_user: UserClaims = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    """
    Return the profile of the currently authenticated user.
    Auth: any role.
    Requirements: 6.1
    """
    return await _service(db).get_profile(current_user.cni)


@router.patch(
    "/users/me",
    response_model=UserProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Update authenticated user's profile",
)
async def update_my_profile(
    request: Request,
    data: UpdateProfileRequest,
    current_user: UserClaims = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    """
    Update nom and/or email for the authenticated user.
    Reads the raw JSON body so the service can detect attempts to mutate
    immutable fields (cni, date_inscription) or perform a role change by a
    non-Admin.
    Auth: any role.
    Requirements: 6.2–6.8
    """
    try:
        raw_body: dict[str, Any] = await request.json()
    except Exception:
        raw_body = {}

    return await _service(db).update_profile(
        cni=current_user.cni,
        data=data,
        requester_role=current_user.role,
        raw_body=raw_body,
    )


@router.post(
    "/users/me/photos",
    response_model=PhotoProfilResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a profile photo",
)
async def upload_photo(
    file: UploadFile,
    current_user: UserClaims = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhotoProfilResponse:
    """
    Upload a profile picture (JPEG / PNG / WebP, max 5 MB).
    Auth: any role.
    Requirements: 7.1–7.8
    """
    return await _service(db).upload_photo(cni=current_user.cni, file=file)


@router.get(
    "/users/me/photos",
    response_model=list[PhotoProfilResponse],
    status_code=status.HTTP_200_OK,
    summary="List profile photo history",
)
async def get_photo_history(
    current_user: UserClaims = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PhotoProfilResponse]:
    """
    Return all profile photos for the authenticated user, ordered newest first.
    Returns an empty list when no photos exist.
    Auth: any role.
    Requirements: 7.9
    """
    return await _service(db).get_photo_history(current_user.cni)


@router.get(
    "/users/me/reports",
    response_model=list[RapportArchiveResponse],
    status_code=status.HTTP_200_OK,
    summary="List archived report history",
)
async def get_report_history(
    current_user: UserClaims = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RapportArchiveResponse]:
    """
    Return all archived reports for the authenticated user, ordered newest first.
    Returns an empty list when no reports exist.
    Auth: any role.
    Requirements: 12.5
    """
    return await _service(db).get_report_history(current_user.cni)


# ── Admin endpoints (Admin role only) ─────────────────────────────────────────

@router.get(
    "/admin/users",
    response_model=list[AdminUserResponse],
    status_code=status.HTTP_200_OK,
    summary="List all registered users (Admin only)",
    dependencies=[Depends(require_role("Admin"))],
)
async def list_all_users(
    db: AsyncSession = Depends(get_db),
) -> list[AdminUserResponse]:
    """
    Return all registered users with their full profile, role, and is_active status.
    Auth: Admin only.
    Requirements: 13.1
    """
    return await _service(db).list_all_users()


@router.patch(
    "/admin/users/{cni}/role",
    response_model=AdminUserResponse,
    status_code=status.HTTP_200_OK,
    summary="Change a user's role (Admin only)",
)
async def update_user_role(
    cni: str,
    data: RoleUpdateRequest,
    current_user: UserClaims = Depends(require_role("Admin")),
    db: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    """
    Change the role of a non-Admin user.
    Raises 403 if the target user is already an Admin.
    Auth: Admin only.
    Requirements: 13.2–13.4
    """
    return await _service(db).update_user_role(
        target_cni=cni,
        new_role=data.role.value,
        requester_role=current_user.role,
    )


@router.patch(
    "/admin/users/{cni}/deactivate",
    status_code=status.HTTP_200_OK,
    summary="Deactivate a user account (Admin only)",
    dependencies=[Depends(require_role("Admin"))],
)
async def deactivate_user(
    cni: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Set the target user's is_active flag to False.
    Idempotent: returns 200 even if the account is already inactive.
    Auth: Admin only.
    Requirements: 13.5–13.7
    """
    await _service(db).deactivate_user(cni)
    return {"message": "Account deactivated."}
