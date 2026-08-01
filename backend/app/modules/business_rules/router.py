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
    require_admin,
)
from app.modules.business_rules.schemas import (
    AdjustmentListResponse,
    AdjustmentRequest,
    AdjustmentResponse,
    AdjustmentSummary,
    ZoneDetail,
    CompatibilityRuleCreate,
    CompatibilityRuleResponse,
    CompatibilityRuleUpdate,
    VerdictEvaluationResponse,
    VerificationRequest,
)
from app.modules.business_rules.service import EaseCalculationService, CompatibilityService

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


# ---------------------------------------------------------------------------
# Module 6 — Fabric / Model / Silhouette Compatibility Engine
# Mounted at /api/v1/compatibility (registered in main.py).
# Requirements: 9.1–9.7, 10.1–10.6, 13.1, 13.6
# ---------------------------------------------------------------------------

compatibility_router = APIRouter()


# ---------------------------------------------------------------------------
# POST /verifications
# Trigger a full compatibility evaluation  (Req 10.1–10.3)
# ---------------------------------------------------------------------------

@compatibility_router.post(
    "/verifications",
    response_model=VerdictEvaluationResponse,
    status_code=201,
    summary="Lancer une évaluation de compatibilité",
    description=(
        "Déclenche l'évaluation complète (tissu × patron × morphologie) pour une "
        "combinaison donnée. Retourne HTTP 201 avec le verdict global et la liste des "
        "zones à risque éventuelles."
    ),
)
async def create_verification(
    body: VerificationRequest,
    current_user: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VerdictEvaluationResponse:
    """
    Req 10.1 — authenticated user triggers evaluation.
    Req 10.2 — 201 response with VerdictEvaluationResponse body.
    Req 10.3 — evaluation persisted; retrievable via GET /verifications/{id}.
    """
    from sqlalchemy import select as _select
    from app.modules.measurements.models import CaptureSession, RawMeasurement
    from app.modules.business_rules.models import MeasurementAdjustment

    # Resolve adjustment_id from session_id + fabric_id when not provided
    if body.adjustment_id is None:
        stmt = (
            _select(MeasurementAdjustment)
            .where(
                MeasurementAdjustment.session_id == body.session_id,
                MeasurementAdjustment.fabric_id == body.fabric_id,
            )
            .order_by(MeasurementAdjustment.calculated_at.desc())
        )
        result = await db.execute(stmt)
        adj = result.scalars().first()
        if adj is None:
            from fastapi import HTTPException as _HTTPException
            raise _HTTPException(
                status_code=422,
                detail=(
                    "Aucun ajustement trouvé pour cette session et ce tissu. "
                    "Calculez d'abord les marges d'aisance."
                ),
            )
        body = body.model_copy(update={"adjustment_id": adj.id})

    # Resolve morphology_id from the session's RawMeasurement silhouette_code
    if body.morphology_id is None:
        stmt = _select(RawMeasurement).where(
            RawMeasurement.session_id == body.session_id
        )
        result = await db.execute(stmt)
        raw = result.scalars().first()
        if raw is None:
            from fastapi import HTTPException as _HTTPException
            raise _HTTPException(
                status_code=422,
                detail="Aucune mensuration validée pour cette session.",
            )
        # silhouette_code is a string like "HOURGLASS"
        # Use a placeholder UUID for morphology_id and pass the real code separately
        import uuid as _uuid
        body = body.model_copy(update={
            "morphology_id": _uuid.UUID("00000000-0000-0000-0000-000000000001"),
            "silhouette_code": raw.silhouette_code,
        })

    # client_id is always the authenticated user
    if body.client_id is None:
        body = body.model_copy(update={"client_id": current_user})

    return await CompatibilityService.verify(body, current_user, db)


# ---------------------------------------------------------------------------
# GET /verifications/{evaluation_id}
# Retrieve an existing evaluation  (Req 10.4–10.5)
# ---------------------------------------------------------------------------

@compatibility_router.get(
    "/verifications/{evaluation_id}",
    response_model=VerdictEvaluationResponse,
    status_code=200,
    summary="Consulter une évaluation de compatibilité",
    description=(
        "Retourne le verdict et les zones à risque d'une évaluation déjà persistée. "
        "HTTP 404 si l'identifiant est inconnu."
    ),
)
async def get_verification(
    evaluation_id: uuid.UUID,
    current_user: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VerdictEvaluationResponse:
    """
    Req 10.4 — returns persisted evaluation with risk zones.
    Req 10.5 — 404 if evaluation_id not found.
    """
    return await CompatibilityService.get_evaluation(evaluation_id, db)


# ---------------------------------------------------------------------------
# POST /compatibility-rules
# Create a new compatibility rule (admin only)  (Req 9.1–9.3)
# ---------------------------------------------------------------------------

@compatibility_router.post(
    "/compatibility-rules",
    response_model=CompatibilityRuleResponse,
    status_code=201,
    summary="Créer une règle de compatibilité",
    description=(
        "Crée une nouvelle règle de compatibilité (cut_type × fabric_property × zone). "
        "Réservé aux administrateurs. HTTP 409 si une règle active identique existe déjà."
    ),
)
async def create_compatibility_rule(
    body: CompatibilityRuleCreate,
    admin_id: uuid.UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> CompatibilityRuleResponse:
    """
    Req 9.1 — admin creates rule with version=1.
    Req 9.2 — 409 on duplicate active (cut_type, fabric_property, zone_id).
    Req 9.5 — require_admin enforces is_admin JWT claim; 403 leaks no rule content.
    """
    return await CompatibilityService.create_rule(body, admin_id, db)


# ---------------------------------------------------------------------------
# PATCH /compatibility-rules/{rule_id}
# Update a compatibility rule (admin only)  (Req 9.3–9.4)
# ---------------------------------------------------------------------------

@compatibility_router.patch(
    "/compatibility-rules/{rule_id}",
    response_model=CompatibilityRuleResponse,
    status_code=200,
    summary="Modifier une règle de compatibilité",
    description=(
        "Met à jour les champs mutables d'une règle existante et incrémente sa version. "
        "Les champs d'identité (cut_type, fabric_property, zone_id) sont immuables : "
        "toute tentative de les modifier est rejetée avec HTTP 422."
    ),
)
async def update_compatibility_rule(
    rule_id: uuid.UUID,
    body: CompatibilityRuleUpdate,
    admin_id: uuid.UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> CompatibilityRuleResponse:
    """
    Req 9.3 — version incremented on every PATCH.
    Req 9.4 — immutable identity fields rejected with 422 (enforced in service).
    Req 9.5 — require_admin enforces is_admin JWT claim.
    """
    return await CompatibilityService.update_rule(rule_id, body, db)


# ---------------------------------------------------------------------------
# GET /compatibility-rules
# List all compatibility rules (admin only)  (Req 9.6–9.7)
# ---------------------------------------------------------------------------

@compatibility_router.get(
    "/compatibility-rules",
    response_model=list[CompatibilityRuleResponse],
    status_code=200,
    summary="Lister les règles de compatibilité",
    description=(
        "Retourne toutes les règles de compatibilité (actives et inactives), "
        "limitées à 200 entrées. Réservé aux administrateurs."
    ),
)
async def list_compatibility_rules(
    admin_id: uuid.UUID = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[CompatibilityRuleResponse]:
    """
    Req 9.6 — returns all rules (active + inactive) up to limit=200.
    Req 9.7 — admin-only access via require_admin.
    """
    return await CompatibilityService.list_rules(db)
