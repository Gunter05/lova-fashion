"""
MeasurementService — business logic for Mensuration creation and history retrieval.

Design reference: Measurement_Service (design.md)
Requirements: 5.1–5.4, 8.1–8.6, 10.1–10.5
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth_user_profile.measurement.repository import (
    MensurationRepository,
    UserNotFoundError,
)
from app.modules.auth_user_profile.measurement.schemas import (
    MensurationCreateRequest,
    MensurationResponse,
)
from app.modules.auth_user_profile.profile.repository import ProfileRepository
from app.modules.auth_user_profile.auth.repository import UserRepository

logger = logging.getLogger(__name__)


def _error(http_status: int, code: str, message: str, field: str | None = None) -> HTTPException:
    """Build an HTTPException whose detail matches the project error-envelope schema."""
    return HTTPException(
        status_code=http_status,
        detail={"error": code, "field": field, "message": message},
    )


class MeasurementService:
    """
    Business logic for:
      - Manual measurement entry creation (Req 8)
      - Measurement history retrieval with RBAC (Req 5, 10)
    """

    def __init__(self, session: AsyncSession) -> None:
        self._repo = MensurationRepository(session)
        self._profile_repo = ProfileRepository(session)
        self._user_repo = UserRepository(session)

    # ── Method 1: Manual measurement creation ────────────────────────────────

    async def create_manual_mensuration(
        self,
        user_id: str,
        data: MensurationCreateRequest,
    ) -> MensurationResponse:
        """
        Create a Mensuration record from a manually submitted request.

        Raises:
            HTTP 404 USER_NOT_FOUND — if the user_id has no matching user.
            HTTP 500 (re-raised)     — on unexpected system failure.
        """
        try:
            record = await self._repo.create_mensuration(
                user_id=user_id,
                tour_poitrine=data.tour_poitrine,
                tour_taille=data.tour_taille,
                tour_hanches=data.tour_hanches,
                longueur_bras=data.longueur_bras,
                hauteur=data.hauteur,
                source_event_hash=None,  # manual entries have no source event hash
            )
        except UserNotFoundError:
            raise _error(
                status.HTTP_404_NOT_FOUND,
                "USER_NOT_FOUND",
                f"No user found with id '{user_id}'.",
            )
        except Exception:
            logger.critical(
                "Unexpected failure while creating mensuration for user_id '%s'. "
                "No partial record was persisted.",
                user_id,
                exc_info=True,
            )
            raise

        return MensurationResponse(
            id_mesure=record.id_mesure,
            user_id=str(record.user_id),
            tour_poitrine=float(record.tour_poitrine),
            tour_taille=float(record.tour_taille),
            tour_hanches=float(record.tour_hanches),
            longueur_bras=float(record.longueur_bras),
            hauteur=float(record.hauteur),
            date_mensuration=record.date_mensuration,
        )

    # ── Method 2: History retrieval with RBAC ────────────────────────────────

    async def get_history(
        self,
        user_id: str,
        requester_id: str,
        requester_role: str,
    ) -> list[MensurationResponse]:
        """
        Return the Mensuration history for target ``user_id``, enforcing RBAC rules.

        Access rules:
          - Client  : can only access their own history (user_id == requester_id).
          - Tailor  : must be explicitly assigned to the target client.
          - Admin   : unrestricted access.

        Raises:
            HTTP 403 FORBIDDEN           — Client requesting another user's history.
            HTTP 403 TAILOR_NOT_ASSIGNED — Tailor not assigned to the target client.
            HTTP 404 USER_NOT_FOUND      — Target user_id does not exist.
        """
        import uuid as _uuid
        try:
            target_uuid = _uuid.UUID(user_id)
            requester_uuid = _uuid.UUID(requester_id)
        except ValueError:
            raise _error(status.HTTP_404_NOT_FOUND, "USER_NOT_FOUND",
                         f"No user found with id '{user_id}'.")

        if requester_role == "Client":
            if user_id != requester_id:
                raise _error(
                    status.HTTP_403_FORBIDDEN,
                    "FORBIDDEN",
                    "Clients may only access their own measurement history.",
                )
            records = await self._repo.get_history_for_user(requester_id)

        elif requester_role == "Tailor":
            is_assigned = await self._profile_repo.is_tailor_assigned(
                requester_uuid, target_uuid
            )
            if not is_assigned:
                raise _error(
                    status.HTTP_403_FORBIDDEN,
                    "TAILOR_NOT_ASSIGNED",
                    f"Tailor '{requester_id}' is not assigned to client '{user_id}'.",
                )
            records = await self._repo.get_history_for_user(user_id)

        else:
            records = await self._repo.get_history_for_user(user_id)

        if not records:
            user = await self._user_repo.get_by_id(target_uuid)
            if user is None:
                raise _error(
                    status.HTTP_404_NOT_FOUND,
                    "USER_NOT_FOUND",
                    f"No user found with id '{user_id}'.",
                )

        return [
            MensurationResponse(
                id_mesure=r.id_mesure,
                user_id=str(r.user_id),
                tour_poitrine=float(r.tour_poitrine),
                tour_taille=float(r.tour_taille),
                tour_hanches=float(r.tour_hanches),
                longueur_bras=float(r.longueur_bras),
                hauteur=float(r.hauteur),
                date_mensuration=r.date_mensuration,
            )
            for r in records
        ]
