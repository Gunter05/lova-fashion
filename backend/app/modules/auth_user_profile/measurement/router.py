"""
Measurement HTTP router for Module 1.

Endpoints:
  POST /users/me/mensurations          — Client: create manual measurement
  GET  /users/me/mensurations          — Client: get own measurement history
  GET  /users/{cni}/mensurations       — Tailor / Admin: get any client's history

Design reference: API Endpoints — Measurement Endpoints (design.md)
Requirements: 5.1–5.4, 8.1–8.6, 10.1–10.5
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth_catalogues.auth.dependencies import (
    UserClaims,
    require_role,
)
from app.modules.auth_catalogues.measurement.schemas import (
    MensurationCreateRequest,
    MensurationResponse,
)
from app.modules.auth_catalogues.measurement.service import MeasurementService

router = APIRouter()


def _service(db: AsyncSession) -> MeasurementService:
    """Instantiate MeasurementService with the current DB session."""
    return MeasurementService(db)


# ── POST /users/me/mensurations ───────────────────────────────────────────────

@router.post(
    "/users/me/mensurations",
    response_model=MensurationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a manual measurement entry (Client only)",
)
async def create_mensuration(
    data: MensurationCreateRequest,
    current_user: UserClaims = Depends(require_role("Client")),
    db: AsyncSession = Depends(get_db),
) -> MensurationResponse:
    """
    Record a new set of body measurements for the authenticated Client.

    All five values (tour_poitrine, tour_taille, tour_hanches, longueur_bras,
    hauteur) must be positive numbers not exceeding 300 cm; violations return
    HTTP 422 before the service is called.

    Auth: Client role only.
    Requirements: 8.1–8.6
    """
    return await _service(db).create_manual_mensuration(
        cni=current_user.cni,
        data=data,
    )


# ── GET /users/me/mensurations ────────────────────────────────────────────────

@router.get(
    "/users/me/mensurations",
    response_model=list[MensurationResponse],
    status_code=status.HTTP_200_OK,
    summary="Get own measurement history (Client only)",
)
async def get_my_mensurations(
    current_user: UserClaims = Depends(require_role("Client")),
    db: AsyncSession = Depends(get_db),
) -> list[MensurationResponse]:
    """
    Return all Mensuration records for the authenticated Client, ordered by
    date_mensuration descending. Returns an empty list if none exist.

    Auth: Client role only.
    Requirements: 10.1, 10.4, 10.5
    """
    return await _service(db).get_history(
        cni=current_user.cni,
        requester_cni=current_user.cni,
        requester_role="Client",
    )


# ── GET /users/{cni}/mensurations ─────────────────────────────────────────────

@router.get(
    "/users/{cni}/mensurations",
    response_model=list[MensurationResponse],
    status_code=status.HTTP_200_OK,
    summary="Get a client's measurement history (Tailor/Admin only)",
)
async def get_user_mensurations(
    cni: str,
    current_user: UserClaims = Depends(require_role("Tailor", "Admin")),
    db: AsyncSession = Depends(get_db),
) -> list[MensurationResponse]:
    """
    Return all Mensuration records for the user identified by ``cni``.

    - Tailor: only for clients explicitly assigned to them. Returns 403 otherwise.
    - Admin: unrestricted access.

    Returns 404 if the target CNI does not correspond to an existing user.

    Auth: Tailor or Admin role.
    Requirements: 5.2–5.4, 10.2–10.4
    """
    return await _service(db).get_history(
        cni=cni,
        requester_cni=current_user.cni,
        requester_role=current_user.role,
    )
