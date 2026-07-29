"""
UserRepository — async data access layer for `users` and `token_denylist`.
All lookups now use id (UUID) or email — cni removed entirely.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserModel, TokenDenylistModel
from app.modules.auth_user_profile.auth.schemas import UserRole


class DuplicateEmailError(Exception):
    """Raised when a registration attempt uses an email already in the database."""


class UserNotFoundError(Exception):
    """Raised when a lookup finds no matching user."""


class UserRepository:
    """Async repository for User and TokenDenylist operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_user(
        self,
        nom: str,
        email: str,
        hashed_password: str,
        role: UserRole,
    ) -> UserModel:
        """
        Persist a new User record. id is auto-generated as UUID.
        Raises DuplicateEmailError if email already exists.
        """
        user = UserModel(
            id=uuid.uuid4(),
            nom=nom,
            email=email,
            mot_de_passe=hashed_password,
            role=role,
            is_active=True,
        )
        self._session.add(user)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            error_str = str(exc.orig).lower()
            if "email" in error_str:
                raise DuplicateEmailError(f"Email '{email}' is already registered.") from exc
            raise
        return user

    async def get_by_email(self, email: str) -> Optional[UserModel]:
        """Return the User with the given email, or None if not found."""
        result = await self._session.execute(
            select(UserModel).where(UserModel.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> Optional[UserModel]:
        """Return the User with the given UUID id, or None if not found."""
        result = await self._session.execute(
            select(UserModel).where(UserModel.id == user_id)
        )
        return result.scalar_one_or_none()

    async def set_is_active(self, user_id: uuid.UUID, is_active: bool) -> UserModel:
        """
        Activate or deactivate a User account by id.
        Raises UserNotFoundError if the id does not exist.
        """
        user = await self.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(f"No user found with id '{user_id}'.")
        await self._session.execute(
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(is_active=is_active)
        )
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def add_jti(self, jti: str, expires_at: datetime) -> None:
        """Add a JWT ID to the denylist. Idempotent."""
        existing = await self._session.get(TokenDenylistModel, jti)
        if existing is not None:
            return
        entry = TokenDenylistModel(jti=jti, expires_at=expires_at)
        self._session.add(entry)
        await self._session.flush()

    async def is_jti_denied(self, jti: str) -> bool:
        """Return True if the given JWT ID is present in the denylist."""
        entry = await self._session.get(TokenDenylistModel, jti)
        return entry is not None
