"""
MensurationRepository — async data access layer for the `mensuration` table.

The `source_event_hash` column enforces idempotency at the DB level for
event-driven measurements from Module 2 (Req 9.5, Property 8).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MensurationModel, UserModel


# ── Domain exceptions ─────────────────────────────────────────────────────────

class UserNotFoundError(Exception):
    """Raised when the target CNI does not correspond to an existing User."""


class DuplicateEventError(Exception):
    """Raised when source_event_hash already exists (duplicate event delivery)."""


# ── Repository ────────────────────────────────────────────────────────────────

class MensurationRepository:
    """Async repository for Mensuration operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_mensuration(
        self,
        user_id: str,
        tour_poitrine: float,
        tour_taille: float,
        tour_hanches: float,
        longueur_bras: float,
        hauteur: float,
        source_event_hash: Optional[str] = None,
    ) -> MensurationModel:
        """
        Persist a new Mensuration record.

        For manual entries, source_event_hash is None.
        For event-driven entries (Module 2), source_event_hash is set and must be unique.

        Raises:
            UserNotFoundError: if the user_id has no corresponding User.
            DuplicateEventError: if source_event_hash is already present (idempotency).
        """
        import uuid as _uuid
        try:
            uid = _uuid.UUID(user_id)
        except ValueError:
            raise UserNotFoundError(f"Invalid user_id format: '{user_id}'.")
        # Verify user exists before inserting
        user_result = await self._session.execute(
            select(UserModel).where(UserModel.id == uid)
        )
        if user_result.scalar_one_or_none() is None:
            raise UserNotFoundError(f"No user found with id '{user_id}'.")

        # For event-driven entries, check idempotency guard before inserting
        if source_event_hash is not None:
            if await self.exists_event_hash(source_event_hash):
                raise DuplicateEventError(
                    f"Event with hash '{source_event_hash}' has already been processed."
                )

        record = MensurationModel(
            id_mesure=str(uuid.uuid4()),
            user_id=uid,
            tour_poitrine=tour_poitrine,
            tour_taille=tour_taille,
            tour_hanches=tour_hanches,
            longueur_bras=longueur_bras,
            hauteur=hauteur,
            date_mensuration=datetime.now(timezone.utc),
            source_event_hash=source_event_hash,
        )
        self._session.add(record)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            error_str = str(exc.orig).lower()
            if "source_event_hash" in error_str or "mensuration_source_event_hash_key" in error_str:
                raise DuplicateEventError(
                    f"Event with hash '{source_event_hash}' has already been processed."
                ) from exc
            raise
        await self._session.refresh(record)
        return record

    async def get_history_for_user(
        self,
        user_id: str,
        order_desc: bool = True,
    ) -> list[MensurationModel]:
        """
        Return all Mensuration records for the given user_id (UUID string).

        Ordered by date_mensuration DESC by default.
        Returns an empty list if the user has no records (never raises).
        """
        import uuid as _uuid
        try:
            uid = _uuid.UUID(user_id)
        except ValueError:
            return []
        order_col = (
            MensurationModel.date_mensuration.desc()
            if order_desc
            else MensurationModel.date_mensuration.asc()
        )
        result = await self._session.execute(
            select(MensurationModel)
            .where(MensurationModel.user_id == uid)
            .order_by(order_col)
        )
        return list(result.scalars().all())

    async def exists_event_hash(self, source_event_hash: str) -> bool:
        """
        Return True if the given source_event_hash already exists in the table.
        Used to prevent duplicate processing of the same Module 2 event (Property 8).
        """
        result = await self._session.execute(
            select(MensurationModel).where(
                MensurationModel.source_event_hash == source_event_hash
            )
        )
        return result.scalar_one_or_none() is not None
