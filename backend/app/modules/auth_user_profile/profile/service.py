"""
Profile_Service — business logic for profile read/update, photo upload,
report archiving, and admin user management.

Design reference: Components and Interfaces; API Endpoints — Profile Endpoints, Admin Endpoints
Requirements: 6.1–6.8, 7.1–7.9, 12.5, 13.1–13.7
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth_catalogues.auth.repository import UserRepository
from app.modules.auth_catalogues.auth.schemas import UserRole
from app.modules.auth_catalogues.profile.repository import (
    ProfileRepository,
    UserNotFoundError,
    DuplicateEmailError,
)
from app.modules.auth_catalogues.profile.schemas import (
    AdminUserResponse,
    PhotoProfilResponse,
    RapportArchiveResponse,
    UpdateProfileRequest,
    UserProfileResponse,
)

logger = logging.getLogger(__name__)

# Accepted MIME types for profile photo uploads
_ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

# Maximum file size: 5 MB in bytes
_MAX_FILE_SIZE = 5_242_880

# Fields that may never be updated via UpdateProfileRequest
_IMMUTABLE_FIELDS = {"cni", "date_inscription"}

# Fields whose presence in the raw dict indicates a role-change attempt
_ROLE_FIELD = "role"


# ── Storage abstraction ───────────────────────────────────────────────────────

class StorageUnavailableError(Exception):
    """Raised when Supabase Storage cannot be reached."""


class SupabaseStorage:
    """
    Thin wrapper around Supabase Storage for profile photo uploads.

    In unit tests this class is monkey-patched / replaced with a mock that
    returns a deterministic URL without making real network calls.
    """

    @staticmethod
    async def upload(cni: str, file: UploadFile) -> str:
        """
        Upload *file* for *cni* and return the public URL.

        Raises StorageUnavailableError when the storage backend is unreachable.
        """
        import uuid as _uuid

        try:
            import httpx  # optional; only needed for real Supabase calls in production
            import os

            supabase_url = os.environ.get("SUPABASE_URL", "")
            supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            bucket = os.environ.get("SUPABASE_PHOTO_BUCKET", "profile-photos")

            if not supabase_url or not supabase_key:
                # Environment not configured — generate a placeholder URL
                # (This branch is hit in local dev without Supabase credentials.)
                object_name = f"{cni}/{_uuid.uuid4()}.jpg"
                return f"https://storage.example.com/photos/{object_name}"

            object_name = f"{cni}/{_uuid.uuid4()}.jpg"
            contents = await file.read()
            await file.seek(0)  # reset for any downstream reads

            async with httpx.AsyncClient() as client:
                upload_url = f"{supabase_url}/storage/v1/object/{bucket}/{object_name}"
                headers = {
                    "Authorization": f"Bearer {supabase_key}",
                    "Content-Type": file.content_type or "application/octet-stream",
                }
                response = await client.post(upload_url, content=contents, headers=headers)
                if response.status_code not in (200, 201):
                    raise StorageUnavailableError(
                        f"Supabase Storage returned {response.status_code}"
                    )

            public_url = (
                f"{supabase_url}/storage/v1/object/public/{bucket}/{object_name}"
            )
            return public_url

        except StorageUnavailableError:
            raise
        except Exception as exc:
            logger.error("Supabase Storage upload failed for cni=%s: %s", cni, exc)
            raise StorageUnavailableError("Storage service unavailable.") from exc


# ── Profile_Service ───────────────────────────────────────────────────────────

class ProfileService:
    """
    Handles profile read/update, profile-picture upload to Supabase Storage,
    report history retrieval, and admin user management.

    Each method receives an AsyncSession so the FastAPI route controls the
    transaction boundary.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._repo = ProfileRepository(session)
        self._user_repo = UserRepository(session)

    # ── Task 16.1 — get_profile ───────────────────────────────────────────────

    async def get_profile(self, cni: str) -> UserProfileResponse:
        """
        Retrieve the profile for *cni*.

        Raises HTTP 404 when the user does not exist.
        Requirements: 6.1
        """
        try:
            user = await self._repo.get_user(cni)
        except UserNotFoundError:
            raise HTTPException(status_code=404, detail={
                "error": "USER_NOT_FOUND",
                "field": "cni",
                "message": f"No user found with CNI '{cni}'.",
            })

        return UserProfileResponse(
            cni=user.cni,
            nom=user.nom,
            email=user.email,
            role=UserRole(user.role),
            date_inscription=user.date_inscription,
        )

    # ── Task 16.2 — update_profile ────────────────────────────────────────────

    async def update_profile(
        self,
        cni: str,
        data: UpdateProfileRequest,
        requester_role: str,
        raw_body: dict[str, Any] | None = None,
    ) -> UserProfileResponse:
        """
        Update nom and/or email for the user identified by *cni*.

        *raw_body* is the original parsed dict (before Pydantic strips unknowns).
        This lets the service detect attempts to set immutable fields (cni,
        date_inscription) or a role field by a non-Admin.

        Raises:
            HTTP 422 IMMUTABLE_FIELD  — raw_body contains 'cni' or 'date_inscription'
            HTTP 403 ROLE_CHANGE_FORBIDDEN — raw_body contains 'role' and caller is not Admin
            HTTP 422 EMPTY_UPDATE     — no recognised updatable fields present
            HTTP 409                  — new email already in use
        Requirements: 6.2–6.8
        """
        if raw_body is None:
            raw_body = {}

        # 1. Reject immutable fields (Req 6.6)
        for field in _IMMUTABLE_FIELDS:
            if field in raw_body:
                raise HTTPException(status_code=422, detail={
                    "error": "IMMUTABLE_FIELD",
                    "field": field,
                    "message": f"Field '{field}' is immutable and cannot be updated.",
                })

        # 2. Reject role change by non-Admin (Req 6.7)
        if _ROLE_FIELD in raw_body:
            if requester_role != UserRole.ADMIN.value and requester_role != UserRole.ADMIN:
                raise HTTPException(status_code=403, detail={
                    "error": "ROLE_CHANGE_FORBIDDEN",
                    "field": "role",
                    "message": "Changing the role field requires Admin privileges.",
                })

        # 3. Reject empty / no-op update body (Req 6.8)
        # Pydantic has already validated email format and nom length; check that at
        # least one of the model's known fields is actually set.
        update_kwargs: dict[str, Any] = {}
        if data.nom is not None:
            update_kwargs["nom"] = data.nom
        if data.email is not None:
            update_kwargs["email"] = str(data.email)

        if not update_kwargs:
            raise HTTPException(status_code=422, detail={
                "error": "EMPTY_UPDATE",
                "field": None,
                "message": "At least one updatable field (nom or email) must be provided.",
            })

        # 4. Persist
        try:
            user = await self._repo.update_user(cni, **update_kwargs)
        except UserNotFoundError:
            raise HTTPException(status_code=404, detail={
                "error": "USER_NOT_FOUND",
                "field": "cni",
                "message": f"No user found with CNI '{cni}'.",
            })
        except DuplicateEmailError:
            raise HTTPException(status_code=409, detail={
                "error": "EMAIL_CONFLICT",
                "field": "email",
                "message": "Email address is already in use by another account.",
            })

        return UserProfileResponse(
            cni=user.cni,
            nom=user.nom,
            email=user.email,
            role=UserRole(user.role),
            date_inscription=user.date_inscription,
        )

    # ── Task 16.3 — upload_photo ──────────────────────────────────────────────

    async def upload_photo(
        self,
        cni: str,
        file: UploadFile,
        storage: type[SupabaseStorage] | None = None,
    ) -> PhotoProfilResponse:
        """
        Validate *file*, upload to Supabase Storage, persist a PhotoProfil record.

        *storage* is injected in tests to avoid real network calls.

        Raises:
            HTTP 422 INVALID_MIME_TYPE — MIME not in {image/jpeg, image/png, image/webp}
            HTTP 422 EMPTY_FILE        — file.size == 0
            HTTP 413 FILE_TOO_LARGE    — file.size > 5 MB
            HTTP 503                   — Supabase Storage unavailable
        Requirements: 7.1–7.8
        """
        if storage is None:
            storage = SupabaseStorage

        # 1. MIME type check (Req 7.5)
        content_type = (file.content_type or "").lower()
        if content_type not in _ALLOWED_MIME_TYPES:
            raise HTTPException(status_code=422, detail={
                "error": "INVALID_MIME_TYPE",
                "field": "file",
                "message": (
                    f"File type '{content_type}' is not accepted. "
                    "Accepted formats: JPEG, PNG, WebP."
                ),
            })

        # 2. Empty file check (Req 7.6)
        # UploadFile.size may be None if the client didn't send Content-Length.
        # In that case we read the content to determine size.
        file_size = file.size
        if file_size is None:
            content = await file.read()
            await file.seek(0)
            file_size = len(content)

        if file_size == 0:
            raise HTTPException(status_code=422, detail={
                "error": "EMPTY_FILE",
                "field": "file",
                "message": "Uploaded file is empty (0 bytes).",
            })

        # 3. Max size check (Req 7.7)
        if file_size > _MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail={
                "error": "FILE_TOO_LARGE",
                "field": "file",
                "message": "Uploaded file exceeds the 5 MB size limit.",
            })

        # 4. Upload to storage (Req 7.3, 7.8)
        try:
            url_photo = await storage.upload(cni, file)
        except StorageUnavailableError as exc:
            logger.error("Supabase Storage unavailable during photo upload for cni=%s: %s", cni, exc)
            raise HTTPException(status_code=503, detail={
                "error": "STORAGE_UNAVAILABLE",
                "field": None,
                "message": "Photo storage service is currently unavailable. Please try again later.",
            })

        # 5. Persist PhotoProfil record (Req 7.1, 7.2, 7.3, 7.4)
        try:
            photo = await self._repo.add_photo(cni, url_photo)
        except UserNotFoundError:
            raise HTTPException(status_code=404, detail={
                "error": "USER_NOT_FOUND",
                "field": "cni",
                "message": f"No user found with CNI '{cni}'.",
            })

        return PhotoProfilResponse(
            id_photo=photo.id_photo,
            url_photo=photo.url_photo,
            date_upload=photo.date_upload,
        )

    # ── Task 16.4 — get_photo_history ─────────────────────────────────────────

    async def get_photo_history(self, cni: str) -> list[PhotoProfilResponse]:
        """
        Return all PhotoProfil records for *cni* ordered by date_upload DESC.
        Returns an empty list when the user has no photos.
        Requirements: 7.9
        """
        photos = await self._repo.get_photos(cni)
        return [
            PhotoProfilResponse(
                id_photo=p.id_photo,
                url_photo=p.url_photo,
                date_upload=p.date_upload,
            )
            for p in photos
        ]

    # ── Task 16.5 — get_report_history ────────────────────────────────────────

    async def get_report_history(self, cni: str) -> list[RapportArchiveResponse]:
        """
        Return all archived report references for *cni* ordered by archived_at DESC.
        Returns an empty list when the user has no archived reports.
        Requirements: 12.5
        """
        rapports = await self._repo.get_rapports(cni)
        return [
            RapportArchiveResponse(
                report_id=r.report_id,
                date_generation=r.date_generation,
                archived_at=r.archived_at,
            )
            for r in rapports
        ]

    # ── Task 17.1 — list_all_users ────────────────────────────────────────────

    async def list_all_users(self) -> list[AdminUserResponse]:
        """
        Return all registered users (Admin operation).
        Requirements: 13.1
        """
        users = await self._repo.list_users()
        return [
            AdminUserResponse(
                cni=u.cni,
                nom=u.nom,
                email=u.email,
                role=UserRole(u.role),
                is_active=u.is_active,
                date_inscription=u.date_inscription,
            )
            for u in users
        ]

    # ── Task 17.2 — update_user_role ──────────────────────────────────────────

    async def update_user_role(
        self,
        target_cni: str,
        new_role: str,
        requester_role: str,
    ) -> AdminUserResponse:
        """
        Change the role of a non-Admin user (Admin-only operation).

        Raises:
            HTTP 404                  — target user not found
            HTTP 403 ADMIN_ROLE_PROTECTED — target user is already an Admin
        Requirements: 13.2–13.4
        """
        # Fetch target user
        try:
            target = await self._repo.get_user(target_cni)
        except UserNotFoundError:
            raise HTTPException(status_code=404, detail={
                "error": "USER_NOT_FOUND",
                "field": "cni",
                "message": f"No user found with CNI '{target_cni}'.",
            })

        # Protect Admin accounts from role reassignment (Req 13.4)
        current_role = target.role
        current_role_value = current_role.value if hasattr(current_role, "value") else str(current_role)
        if current_role_value == UserRole.ADMIN.value:
            raise HTTPException(status_code=403, detail={
                "error": "ADMIN_ROLE_PROTECTED",
                "field": None,
                "message": "The role of an Admin user cannot be changed through this endpoint.",
            })

        # Persist the role change
        updated = await self._repo.update_role(target_cni, UserRole(new_role))

        return AdminUserResponse(
            cni=updated.cni,
            nom=updated.nom,
            email=updated.email,
            role=UserRole(updated.role),
            is_active=updated.is_active,
            date_inscription=updated.date_inscription,
        )

    # ── Task 17.3 — deactivate_user ───────────────────────────────────────────

    async def deactivate_user(self, target_cni: str) -> None:
        """
        Deactivate a user account (set is_active = False).

        Idempotent: if the account is already inactive, returns without
        making any modification (Req 13.7).

        Raises HTTP 404 when the target user does not exist.
        Requirements: 13.5–13.7
        """
        # Fetch target user
        try:
            target = await self._repo.get_user(target_cni)
        except UserNotFoundError:
            raise HTTPException(status_code=404, detail={
                "error": "USER_NOT_FOUND",
                "field": "cni",
                "message": f"No user found with CNI '{target_cni}'.",
            })

        # Idempotent: already inactive — return without modifying (Req 13.7)
        if not target.is_active:
            return

        # Deactivate via UserRepository (which holds set_is_active)
        await self._user_repo.set_is_active(target_cni, False)
