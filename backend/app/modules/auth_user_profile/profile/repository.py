"""
ProfileRepository — async data access layer for profile, photo, rapport archive,
and tailor-client assignment operations.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    UserModel,
    PhotoProfilModel,
    RapportArchiveModel,
    TailorClientAssignmentModel,
)
from app.modules.auth_catalogues.auth.schemas import UserRole


# ── Domain exceptions ─────────────────────────────────────────────────────────

class UserNotFoundError(Exception):
    """Raised when a target CNI does not correspond to an existing User."""


class DuplicateEmailError(Exception):
    """Raised when an email update conflicts with an existing User's email."""


class DuplicateRapportError(Exception):
    """Raised (and silently swallowed) when a report_id is already archived for a CNI."""


# ── Repository ────────────────────────────────────────────────────────────────

class ProfileRepository:
    """Async repository for profile, photo, rapport archive, and assignment operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── User profile ──────────────────────────────────────────────────────────

    async def get_user(self, cni: str) -> UserModel:
        """
        Return the User with the given CNI.
        Raises UserNotFoundError if not found.
        """
        result = await self._session.execute(
            select(UserModel).where(UserModel.cni == cni)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise UserNotFoundError(f"No user found with CNI '{cni}'.")
        return user

    async def update_user(
        self,
        cni: str,
        nom: Optional[str] = None,
        email: Optional[str] = None,
    ) -> UserModel:
        """
        Update nom and/or email for the User with the given CNI.

        Raises:
            UserNotFoundError: if cni does not exist.
            DuplicateEmailError: if the new email is already used by another User.
        """
        user = await self.get_user(cni)
        if nom is not None:
            user.nom = nom
        if email is not None:
            user.email = email
        self._session.add(user)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            error_str = str(exc.orig).lower()
            if "email" in error_str:
                raise DuplicateEmailError(f"Email '{email}' is already in use.") from exc
            raise
        await self._session.refresh(user)
        return user

    async def list_users(self) -> list[UserModel]:
        """Return all registered Users (Admin operation)."""
        result = await self._session.execute(select(UserModel))
        return list(result.scalars().all())

    async def update_role(self, cni: str, new_role: UserRole) -> UserModel:
        """
        Update the role of the User with the given CNI.
        Raises UserNotFoundError if not found.
        """
        user = await self.get_user(cni)
        user.role = new_role
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return user

    # ── Photo profil ──────────────────────────────────────────────────────────

    async def add_photo(self, cni: str, url_photo: str) -> PhotoProfilModel:
        """
        Create a new PhotoProfil record for the User.
        Raises UserNotFoundError if the CNI does not exist.
        """
        # verify user exists
        await self.get_user(cni)
        photo = PhotoProfilModel(
            id_photo=str(uuid.uuid4()),
            cni=cni,
            url_photo=url_photo,
            date_upload=datetime.now(timezone.utc),
        )
        self._session.add(photo)
        await self._session.flush()
        await self._session.refresh(photo)
        return photo

    async def get_photos(self, cni: str) -> list[PhotoProfilModel]:
        """
        Return all PhotoProfil records for the User, ordered by date_upload DESC.
        """
        result = await self._session.execute(
            select(PhotoProfilModel)
            .where(PhotoProfilModel.cni == cni)
            .order_by(PhotoProfilModel.date_upload.desc())
        )
        return list(result.scalars().all())

    # ── Rapport archive ───────────────────────────────────────────────────────

    async def add_rapport(
        self,
        cni: str,
        report_id: str,
        date_generation: datetime,
    ) -> Optional[RapportArchiveModel]:
        """
        Archive a report reference for the User.

        Returns the created RapportArchiveModel, or None if the (cni, report_id) pair
        already exists (idempotent — duplicate is silently discarded).

        Raises UserNotFoundError if the CNI does not exist.
        """
        await self.get_user(cni)
        rapport = RapportArchiveModel(
            id=str(uuid.uuid4()),
            cni=cni,
            report_id=report_id,
            date_generation=date_generation,
            archived_at=datetime.now(timezone.utc),
        )
        self._session.add(rapport)
        try:
            await self._session.flush()
        except IntegrityError:
            # Unique constraint on (cni, report_id) — duplicate, discard silently
            await self._session.rollback()
            return None
        await self._session.refresh(rapport)
        return rapport

    async def get_rapports(self, cni: str) -> list[RapportArchiveModel]:
        """
        Return all archived report references for the User, ordered by archived_at DESC.
        """
        result = await self._session.execute(
            select(RapportArchiveModel)
            .where(RapportArchiveModel.cni == cni)
            .order_by(RapportArchiveModel.archived_at.desc())
        )
        return list(result.scalars().all())

    # ── Tailor-client assignment ──────────────────────────────────────────────

    async def is_tailor_assigned(self, tailor_cni: str, client_cni: str) -> bool:
        """
        Return True if the Tailor is explicitly assigned to the Client.
        """
        result = await self._session.execute(
            select(TailorClientAssignmentModel).where(
                TailorClientAssignmentModel.tailor_cni == tailor_cni,
                TailorClientAssignmentModel.client_cni == client_cni,
            )
        )
        return result.scalar_one_or_none() is not None
