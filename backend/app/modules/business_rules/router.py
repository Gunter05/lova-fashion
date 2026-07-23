"""
API router for Module 5 — Ease Allowance Calculation Engine.
Tasks T-06.1 – T-06.3 — Design §5

Mounted at /api/v1/ease (registered in main.py).
All endpoints require Authorization: Bearer <JWT>.

Endpoints
---------
POST   /adjustments                          Compute (or recompute) ease adjustment  201/200
GET    /adjustments/{adjustment_id}          Retrieve a specific adjustment           200
GET    /sessions/{session_id}/adjustments    List all adjustments for a session       200
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.business_rules.dependencies import (
    get_current_user,
    get_db,
)
from app.modules.business_rules.schemas import (
    AdjustmentListResponse,
    AdjustmentRequest,
    AdjustmentResponse,
    AdjustmentSummary,
    ZoneDetail,
)
from app.modules.business_rules.service import EaseCalculationService

router = APIRouter()


# ---------------------------------------------------------------------------
# T-06.1 — POST /adjustments
# Compute (or recompute) an ease adjustment  (AC-01.1 – AC-01.6)
# ---------------------------------------------------------------------------

@router.post(
    "/adjustments",
    response_model=AdjustmentResponse,
    summary="Calculer l'aisance pour un tissu donné",
    description=(
        "Prend une session de mesure validée et un tissu du catalogue, "
        "applique les règles d'aisance selon la catégorie d'élasticité du tissu, "
        "et retourne les mesures finales ajustées. "
        "Retourne HTTP 201 pour un nouvel ajustement, HTTP 200 si le calcul existant "
        "est remplacé (même paire session + tissu)."
    ),
)
async def compute_adjustment(
    body: AdjustmentRequest,
    response: Response,
    current_user: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdjustmentResponse:
    """
    AC-01.1 — 401 if no valid JWT.
    AC-01.2 — 403/404 if session missing or owned by another user.
    AC-01.3 — 424 if session has no completed raw measurement.
    AC-01.4 — 404 if fabric_id not found in catalog.
    AC-01.5 — 201 for new record.
    AC-01.6 — 200 for overwritten record (upsert on session+fabric uniqueness).
    """
    adjustment, is_new = await EaseCalculationService.compute_adjustment(
        user_id=current_user,
        session_id=body.session_id,
        fabric_id=body.fabric_id,
        db=db,
    )

    # Set response status before returning (201 for new, 200 for overwrite)
    response.status_code = 201 if is_new else 200

    # We need fabric metadata to build AdjustmentResponse — re-fetch from service
    detail = await EaseCalculationService.get_adjustment(
        adjustment_id=adjustment.id,
        user_id=current_user,
        db=db,
    )

    return _build_adjustment_response(detail)


# ---------------------------------------------------------------------------
# T-06.2 — GET /adjustments/{adjustment_id}
# Retrieve a specific adjustment  (AC-05.1, AC-05.2, AC-07.1)
# ---------------------------------------------------------------------------

@router.get(
    "/adjustments/{adjustment_id}",
    response_model=AdjustmentResponse,
    summary="Consulter un ajustement spécifique",
    description=(
        "Retourne le détail complet d'un ajustement : valeurs brutes, "
        "aisance appliquée par zone, et mesures ajustées finales. "
        "Inclut un avertissement d'intégrité si la session source n'est plus valide."
    ),
)
async def get_adjustment(
    adjustment_id: uuid.UUID,
    current_user: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdjustmentResponse:
    """
    AC-05.1 — Returns full adjustment detail including per-zone breakdown.
    AC-05.2 — 403 if adjustment belongs to a session owned by another user.
    AC-07.1 — data_integrity_warning=True if source session status ≠ 'success'.
    """
    detail = await EaseCalculationService.get_adjustment(
        adjustment_id=adjustment_id,
        user_id=current_user,
        db=db,
    )
    return _build_adjustment_response(detail)


# ---------------------------------------------------------------------------
# T-06.3 — GET /sessions/{session_id}/adjustments
# List all adjustments for a session  (AC-06.1, AC-06.2)
# ---------------------------------------------------------------------------

@router.get(
    "/sessions/{session_id}/adjustments",
    response_model=AdjustmentListResponse,
    summary="Lister les ajustements d'une session",
    description=(
        "Retourne la liste de tous les ajustements calculés pour une session donnée, "
        "triés du plus récent au plus ancien. "
        "Permet de comparer l'impact de différents tissus sur les mesures de coupe."
    ),
)
async def list_adjustments(
    session_id: uuid.UUID,
    current_user: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdjustmentListResponse:
    """
    AC-06.1 — Returns list ordered by calculated_at DESC.
    AC-06.2 — Returns empty list (total: 0) when no adjustments exist yet.
    """
    items = await EaseCalculationService.list_adjustments(
        session_id=session_id,
        user_id=current_user,
        db=db,
    )

    summaries = [
        AdjustmentSummary(
            adjustment_id=item["adjustment"].id,
            fabric_id=item["adjustment"].fabric_id,
            fabric_name=item["fabric_name"],
            elasticity_category=item["elasticity_category"],
            ease_source=item["adjustment"].ease_source,
            adjusted_bust_cm=item["adjustment"].adjusted_bust_cm,
            adjusted_waist_cm=item["adjustment"].adjusted_waist_cm,
            adjusted_hips_cm=item["adjustment"].adjusted_hips_cm,
            calculated_at=item["adjustment"].calculated_at,
        )
        for item in items
    ]

    return AdjustmentListResponse(adjustments=summaries, total=len(summaries))


# ---------------------------------------------------------------------------
# Private builder — assembles AdjustmentResponse from service dict
# ---------------------------------------------------------------------------

def _build_adjustment_response(detail: dict) -> AdjustmentResponse:
    """
    Convert the enriched dict returned by EaseCalculationService.get_adjustment()
    into a validated AdjustmentResponse schema instance.
    """
    adj = detail["adjustment"]
    return AdjustmentResponse(
        adjustment_id=adj.id,
        session_id=adj.session_id,
        fabric_id=adj.fabric_id,
        fabric_name=detail["fabric_name"],
        elasticity_category=detail["elasticity_category"],
        ease_source=adj.ease_source,
        bust=ZoneDetail(
            raw_cm=adj.raw_bust_cm,
            ease_cm=adj.bust_ease_cm,
            adjusted_cm=adj.adjusted_bust_cm,
        ),
        waist=ZoneDetail(
            raw_cm=adj.raw_waist_cm,
            ease_cm=adj.waist_ease_cm,
            adjusted_cm=adj.adjusted_waist_cm,
        ),
        hips=ZoneDetail(
            raw_cm=adj.raw_hips_cm,
            ease_cm=adj.hips_ease_cm,
            adjusted_cm=adj.adjusted_hips_cm,
        ),
        calculated_at=adj.calculated_at,
        data_integrity_warning=detail.get("data_integrity_warning", False),
    )
