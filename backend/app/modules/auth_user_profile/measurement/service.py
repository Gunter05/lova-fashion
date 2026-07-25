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
        cni: str,
        data: MensurationCreateRequest,
    ) -> MensurationResponse:
        """
        Create a Mensuration record from a manually submitted request.

        Note: Pydantic schema (MensurationCreateRequest) already validates that all
        five values are > 0 and ≤ 300 cm — any violation returns HTTP 422 before
        this method is ever called (Req 8.3, 8.4).

        Raises:
            HTTP 404 USER_NOT_FOUND — if the CNI has no matching user.
            HTTP 500 (re-raised)     — on unexpected system failure (logged CRITICAL, Req 8.5).
        """
        try:
            record = await self._repo.create_mensuration(
                cni=cni,
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
                f"No user found with CNI '{cni}'.",
            )
        except Exception:
            # Req 8.5 — unexpected system failure: log CRITICAL and re-raise
            logger.critical(
                "Unexpected failure while creating mensuration for CNI '%s'. "
                "No partial record was persisted.",
                cni,
                exc_info=True,
            )
            raise

        return MensurationResponse(
            id_mesure=record.id_mesure,
            cni=record.cni,
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
        cni: str,
        requester_cni: str,
        requester_role: str,
    ) -> list[MensurationResponse]:
        """
        Return the Mensuration history for target ``cni``, enforcing RBAC rules.

        Access rules:
          - Client  : can only access their own history (cni == requester_cni).
          - Tailor  : must be explicitly assigned to the target client.
          - Admin   : unrestricted access to any user's history.

        If the query returns an empty list AND the target user does not exist,
        HTTP 404 is raised (Req 10, also guards GET /users/{cni}/mensurations).

        Raises:
            HTTP 403 FORBIDDEN             — Client requesting another user's history.
            HTTP 403 TAILOR_NOT_ASSIGNED   — Tailor not assigned to the target client.
            HTTP 404 USER_NOT_FOUND        — Target CNI does not exist.
        """
        if requester_role == "Client":
            # Clients can only see their own history (Req 5.1, 10.1)
            if cni != requester_cni:
                raise _error(
                    status.HTTP_403_FORBIDDEN,
                    "FORBIDDEN",
                    "Clients may only access their own measurement history.",
                )
            records = await self._repo.get_history_for_cni(requester_cni)

        elif requester_role == "Tailor":
            # Tailors may only read history for explicitly assigned clients (Req 5.2, 5.4, 10.2–10.3)
            is_assigned = await self._profile_repo.is_tailor_assigned(requester_cni, cni)
            if not is_assigned:
                raise _error(
                    status.HTTP_403_FORBIDDEN,
                    "TAILOR_NOT_ASSIGNED",
                    f"Tailor '{requester_cni}' is not assigned to client '{cni}'.",
                )
            records = await self._repo.get_history_for_cni(cni)

        else:
            # Admin — unrestricted (Req 5.3, 13.x)
            records = await self._repo.get_history_for_cni(cni)

        # If no records, check whether the target user actually exists.
        # An empty list is valid for a user who has no measurements (Req 10.5).
        # But if the user does not exist at all, return 404.
        if not records:
            user = await self._user_repo.get_by_cni(cni)
            if user is None:
                raise _error(
                    status.HTTP_404_NOT_FOUND,
                    "USER_NOT_FOUND",
                    f"No user found with CNI '{cni}'.",
                )

        return [
            MensurationResponse(
                id_mesure=r.id_mesure,
                cni=r.cni,
                tour_poitrine=float(r.tour_poitrine),
                tour_taille=float(r.tour_taille),
                tour_hanches=float(r.tour_hanches),
                longueur_bras=float(r.longueur_bras),
                hauteur=float(r.hauteur),
                date_mensuration=r.date_mensuration,
            )
            for r in records
        ]
