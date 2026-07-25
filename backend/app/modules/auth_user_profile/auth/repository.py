"""
UserRepository — async data access layer for the `users` and `token_denylist` tables.

Raises typed domain exceptions (DuplicateCNIError, DuplicateEmailError) on constraint
violations so the service layer can map them cleanly to HTTP 409 responses.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserModel, TokenDenylistModel
from app.modules.auth_user_profile.auth.schemas import UserRole


# ── Domain exceptions ─────────────────────────────────────────────────────────

class DuplicateCNIError(Exception):
    """Raised when a registration attempt uses a CNI already in the database."""


class DuplicateEmailError(Exception):
    """Raised when a registration attempt uses an email already in the database."""


class UserNotFoundError(Exception):
    """Raised when a lookup finds no matching user."""


# ── Repository ────────────────────────────────────────────────────────────────

class UserRepository:
    """Async repository for User and TokenDenylist operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── User CRUD ─────────────────────────────────────────────────────────────

    async def create_user(
        self,
        cni: str,
        nom: str,
        email: str,
        hashed_password: str,
        role: UserRole,
    ) -> UserModel:
        """
        Persist a new User record.

        Raises:
            DuplicateCNIError: if cni already exists.
            DuplicateEmailError: if email already exists.
        """
        user = UserModel(
            cni=cni,
            nom=nom,
            email=email,
            mot_de_passe=hashed_password,
            role=role,
            is_active=True,
        )
        self._session.add(user)
        try:
            await self._session.flush()  # send INSERT without committing
        except IntegrityError as exc:
            await self._session.rollback()
            error_str = str(exc.orig).lower()
            if "users_pkey" in error_str or "cni" in error_str:
                raise DuplicateCNIError(f"CNI '{cni}' is already registered.") from exc
            if "users_email_key" in error_str or "email" in error_str:
                raise DuplicateEmailError(f"Email '{email}' is already registered.") from exc
            raise  # unexpected constraint — re-raise
        return user

    async def get_by_email(self, email: str) -> Optional[UserModel]:
        """Return the User with the given email, or None if not found."""
        result = await self._session.execute(
            select(UserModel).where(UserModel.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_cni(self, cni: str) -> Optional[UserModel]:
        """Return the User with the given CNI, or None if not found."""
        result = await self._session.execute(
            select(UserModel).where(UserModel.cni == cni)
        )
        return result.scalar_one_or_none()

    async def set_is_active(self, cni: str, is_active: bool) -> UserModel:
        """
        Activate or deactivate a User account.

        Returns the updated UserModel.
        Raises UserNotFoundError if the CNI does not exist.
        """
        user = await self.get_by_cni(cni)
        if user is None:
            raise UserNotFoundError(f"No user found with CNI '{cni}'.")
        await self._session.execute(
            update(UserModel)
            .where(UserModel.cni == cni)
            .values(is_active=is_active)
        )
        await self._session.flush()
        # Refresh to get the updated state
        await self._session.refresh(user)
        return user

    # ── Token denylist ────────────────────────────────────────────────────────

    async def add_jti(self, jti: str, expires_at: datetime) -> None:
        """
        Add a JWT ID to the denylist (logout invalidation).
        Idempotent: if the jti already exists the insert is silently ignored.
        """
        existing = await self._session.get(TokenDenylistModel, jti)
        if existing is not None:
            return  # already denied — idempotent
        entry = TokenDenylistModel(jti=jti, expires_at=expires_at)
        self._session.add(entry)
        await self._session.flush()

    async def is_jti_denied(self, jti: str) -> bool:
        """Return True if the given JWT ID is present in the denylist."""
        entry = await self._session.get(TokenDenylistModel, jti)
        return entry is not None
