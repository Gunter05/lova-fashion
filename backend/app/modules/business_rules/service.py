"""
Service layer for Module 5 — Ease Allowance Calculation Engine.
Tasks T-04.1 – T-04.7 — Design §7, §8

Public surface
--------------
EaseCalculationService
    .compute_adjustment(user_id, session_id, fabric_id, db)  → (MeasurementAdjustment, is_new)  T-04.5
    .get_adjustment(adjustment_id, user_id, db)              → dict                             T-04.6
    .list_adjustments(session_id, user_id, db)               → list[dict]                       T-04.7

Private helpers
    _load_session_or_raise(session_id, user_id, db)          → CaptureSession                   T-04.1
    _load_raw_measurement_or_raise(session_id, db)           → RawMeasurement                   T-04.2
    _load_fabric_or_raise(fabric_id, db)                     → (fabric_name, elasticity_cat)    T-04.3
    _upsert_adjustment(...)                                   → (MeasurementAdjustment, is_new)  T-04.4
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.business_rules.engine import EaseEngine, EaseInput
from app.modules.business_rules.models import MeasurementAdjustment
from app.modules.measurements.models import CaptureSession, RawMeasurement

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# T-04.1 — Load capture session with ownership check
# ---------------------------------------------------------------------------

async def _load_session_or_raise(
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> CaptureSession:
    """
    Load a CaptureSession by PK and verify ownership.

    Raises
    ------
    HTTPException 404 — session not found.
    HTTPException 403 — session belongs to a different user.
    AC-01.2 · Design §7
    """
    session: CaptureSession | None = await db.get(CaptureSession, session_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} introuvable.",
        )

    # Normalize both sides to uuid.UUID before comparing.
    # SQLite + aiosqlite may deserialize UUID columns as 32-char hex strings
    # instead of uuid.UUID objects (Python 3.14 + SQLAlchemy edge case).
    def _to_uuid(v) -> uuid.UUID:
        return v if isinstance(v, uuid.UUID) else uuid.UUID(str(v))

    session_uid = _to_uuid(session.user_id)
    expected_uid = _to_uuid(user_id)
    logger.debug(
        "_load_session_or_raise: session.user_id=%r (type=%s) user_id=%r (type=%s) match=%s",
        session.user_id, type(session.user_id).__name__,
        user_id, type(user_id).__name__,
        session_uid == expected_uid,
    )
    if session_uid != expected_uid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous n'êtes pas autorisé à accéder à cette session.",
        )

    return session


# ---------------------------------------------------------------------------
# T-04.2 — Load raw measurement with 424 guard
# ---------------------------------------------------------------------------

async def _load_raw_measurement_or_raise(
    session_id: uuid.UUID,
    db: AsyncSession,
) -> RawMeasurement:
    """
    Load the RawMeasurement for a session.
    Raises HTTP 424 if the session has no completed measurement yet.

    AC-01.3, AC-07.1 · Design §7
    """
    stmt = select(RawMeasurement).where(RawMeasurement.session_id == session_id)
    result = await db.execute(stmt)
    raw: RawMeasurement | None = result.scalars().first()

    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail=(
                "Aucune mensuration validée pour cette session. "
                "Complétez d'abord la prise de mesure."
            ),
        )

    return raw


# ---------------------------------------------------------------------------
# T-04.3 — Load fabric + elasticity category
# ---------------------------------------------------------------------------

async def _load_fabric_or_raise(
    fabric_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[str, str | None]:
    """
    Join fabrics + fabric_categories to get fabric_name and elasticity_category.

    Returns
    -------
    (fabric_name, elasticity_category)
        elasticity_category is None when the fabric has no category or the
        category has no reference_rigidity_level — triggers default fallback.

    Raises
    ------
    HTTPException 404 — fabric_id not found in catalog.
    AC-01.4 · Design §8
    """
    sql = text(
        """
        SELECT
            f.fabric_name,
            fc.reference_rigidity_level AS elasticity_category
        FROM fabrics f
        LEFT JOIN fabric_categories fc ON fc.category_id = f.category_id
        WHERE f.fabric_id = :fabric_id
        """
    )
    result = await db.execute(sql, {"fabric_id": str(fabric_id)})
    row = result.mappings().first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tissu introuvable dans le catalogue.",
        )

    return row["fabric_name"], row["elasticity_category"]


# ---------------------------------------------------------------------------
# T-04.4 — Upsert measurement_adjustments
# ---------------------------------------------------------------------------

async def _upsert_adjustment(
    session_id: uuid.UUID,
    fabric_id: uuid.UUID,
    raw: RawMeasurement,
    output: Any,          # EaseOutput from engine
    db: AsyncSession,
) -> tuple[MeasurementAdjustment, bool]:
    """
    Insert or update the adjustment record on (session_id, fabric_id).

    Uses PostgreSQL's INSERT … ON CONFLICT DO UPDATE (upsert) so that
    re-computing with the same fabric overwrites the stale record (AC-01.6).

    Returns
    -------
    (adjustment, is_new)
        is_new : True  → HTTP 201 (new record created)
                 False → HTTP 200 (existing record overwritten)
    AC-01.5, AC-01.6 · Design §8
    """
    new_id = uuid.uuid4()
    values = dict(
        id=new_id,
        session_id=session_id,
        fabric_id=fabric_id,
        raw_bust_cm=Decimal(str(raw.bust_cm)),
        raw_waist_cm=Decimal(str(raw.waist_cm)),
        raw_hips_cm=Decimal(str(raw.hips_cm)),
        bust_ease_cm=Decimal(str(output.bust.ease_cm)),
        waist_ease_cm=Decimal(str(output.waist.ease_cm)),
        hips_ease_cm=Decimal(str(output.hips.ease_cm)),
        adjusted_bust_cm=Decimal(str(output.bust.adjusted_cm)),
        adjusted_waist_cm=Decimal(str(output.waist.adjusted_cm)),
        adjusted_hips_cm=Decimal(str(output.hips.adjusted_cm)),
        ease_source=output.ease_source,
    )

    stmt = (
        pg_insert(MeasurementAdjustment)
        .values(**values)
        .on_conflict_do_update(
            constraint="uq_adjustment_session_fabric",
            set_=dict(
                raw_bust_cm=values["raw_bust_cm"],
                raw_waist_cm=values["raw_waist_cm"],
                raw_hips_cm=values["raw_hips_cm"],
                bust_ease_cm=values["bust_ease_cm"],
                waist_ease_cm=values["waist_ease_cm"],
                hips_ease_cm=values["hips_ease_cm"],
                adjusted_bust_cm=values["adjusted_bust_cm"],
                adjusted_waist_cm=values["adjusted_waist_cm"],
                adjusted_hips_cm=values["adjusted_hips_cm"],
                ease_source=values["ease_source"],
                updated_at=text("now()"),
            ),
        )
        .returning(MeasurementAdjustment.id)
    )

    result = await db.execute(stmt)
    returned_id: uuid.UUID = result.scalar_one()
    await db.flush()

    # Determine if this was a new insert or an overwrite
    is_new = returned_id == new_id

    # Reload the full ORM object (RETURNING only gives us the id)
    adjustment: MeasurementAdjustment = await db.get(MeasurementAdjustment, returned_id)
    return adjustment, is_new


# ---------------------------------------------------------------------------
# EaseCalculationService
# ---------------------------------------------------------------------------

_engine = EaseEngine()


class EaseCalculationService:
    """
    Orchestrates all ease calculation operations.
    Injected with an AsyncSession scoped to the current HTTP request.
    """

    # ------------------------------------------------------------------
    # T-04.5 — compute_adjustment
    # ------------------------------------------------------------------

    @staticmethod
    async def compute_adjustment(
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        fabric_id: uuid.UUID,
        db: AsyncSession,
    ) -> tuple[MeasurementAdjustment, bool]:
        """
        Full computation pipeline:
            Guard 1 — session ownership              (AC-01.2)
            Guard 2 — session has raw measurement    (AC-01.3)
            Guard 3 — fabric exists in catalog       (AC-01.4)
            Calculate via EaseEngine                 (US-02, US-03, US-04)
            Log all warnings                         (AC-02.4, AC-04.1, AC-04.2)
            Upsert into measurement_adjustments      (AC-01.5, AC-01.6)

        Returns
        -------
        (adjustment, is_new)  — passed to router to set 201 vs 200.
        """
        # Guard 1
        await _load_session_or_raise(session_id, user_id, db)

        # Guard 2
        raw = await _load_raw_measurement_or_raise(session_id, db)

        # Guard 3
        fabric_name, elasticity_category = await _load_fabric_or_raise(fabric_id, db)

        # Calculate
        output = _engine.compute(
            EaseInput(
                bust_cm=float(raw.bust_cm),
                waist_cm=float(raw.waist_cm),
                hips_cm=float(raw.hips_cm),
                elasticity_category=elasticity_category,
            )
        )

        # Log all warnings (Design §11)
        for warning in output.warnings:
            logger.warning(
                "EaseEngine [session=%s fabric=%s]: %s",
                session_id,
                fabric_id,
                warning,
            )

        # Upsert
        adjustment, is_new = await _upsert_adjustment(
            session_id, fabric_id, raw, output, db
        )

        return adjustment, is_new

    # ------------------------------------------------------------------
    # T-04.6 — get_adjustment
    # ------------------------------------------------------------------

    @staticmethod
    async def get_adjustment(
        adjustment_id: uuid.UUID,
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> dict:
        """
        Load a specific adjustment, assert ownership via session join,
        enrich with fabric metadata, set data_integrity_warning flag.

        AC-05.1, AC-05.2, AC-07.1 · Design §5.2
        """
        adjustment: MeasurementAdjustment | None = await db.get(
            MeasurementAdjustment, adjustment_id
        )

        if adjustment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Ajustement {adjustment_id} introuvable.",
            )

        # Ownership check via session (AC-05.2)
        session: CaptureSession | None = await db.get(CaptureSession, adjustment.session_id)
        if session is None or session.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous n'êtes pas autorisé à accéder à cet ajustement.",
            )

        # Enrich with fabric metadata
        fabric_name, elasticity_category = await _load_fabric_or_raise(
            adjustment.fabric_id, db
        )

        # data_integrity_warning: source session is no longer successful (AC-07.1)
        data_integrity_warning = session.status != "success"

        return {
            "adjustment": adjustment,
            "fabric_name": fabric_name,
            "elasticity_category": elasticity_category,
            "data_integrity_warning": data_integrity_warning,
        }

    # ------------------------------------------------------------------
    # T-04.7 — list_adjustments
    # ------------------------------------------------------------------

    @staticmethod
    async def list_adjustments(
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> list[dict]:
        """
        Return all adjustments for a session, newest first.
        Verifies session ownership before querying.

        AC-06.1, AC-06.2 · Design §5.3
        """
        # Ownership check
        await _load_session_or_raise(session_id, user_id, db)

        stmt = (
            select(MeasurementAdjustment)
            .where(MeasurementAdjustment.session_id == session_id)
            .order_by(MeasurementAdjustment.calculated_at.desc())
        )
        result = await db.execute(stmt)
        adjustments = result.scalars().all()

        # Enrich each item with fabric metadata
        items: list[dict] = []
        for adj in adjustments:
            try:
                fabric_name, elasticity_category = await _load_fabric_or_raise(
                    adj.fabric_id, db
                )
            except HTTPException:
                # Fabric was deleted after adjustment was created — degrade gracefully
                fabric_name = "Tissu supprimé"
                elasticity_category = None

            items.append({
                "adjustment": adj,
                "fabric_name": fabric_name,
                "elasticity_category": elasticity_category,
            })

        return items


# ===========================================================================
# Module 6 — Fabric / Model / Silhouette Compatibility Engine
# Tasks 5.1, 5.2, 5.3, 5.4
# Requirements: 1.1–1.12, 2.1–2.7, 3.1–3.9, 4.1–4.5, 5.1–5.6, 6.1–6.4,
#               7.1–7.8, 9.1–9.7, 10.4–10.5, 11.1–11.4, 12.1–12.4
# ===========================================================================

from sqlalchemy.exc import IntegrityError

from app.modules.business_rules.engine import (
    RuleEvaluator,
    RuleInput,
    RuleRecord,
    RiskZoneDict,
)
from app.modules.business_rules.models import (
    CompatibilityRule,
    ModelMorphology,
    VerdictEvaluation,
    RiskZone,
)
from app.modules.business_rules.schemas import (
    VerificationRequest,
    CompatibilityRuleCreate,
    CompatibilityRuleUpdate,
    CompatibilityRuleResponse,
    VerdictEvaluationResponse,
)
from app.modules.auth_catalogues.models import (
    Model,
    ModelStatusEnum,
    Fabric,
    FabricCategory,
    ModelFabric,
)

# ---------------------------------------------------------------------------
# Task 5.1 — Private data-loading helpers
# ---------------------------------------------------------------------------


async def _load_adjustment_or_422(
    adjustment_id: uuid.UUID,
    db: AsyncSession,
) -> MeasurementAdjustment:
    """
    Load MeasurementAdjustment by PK and validate adjusted measurement values.

    Raises HTTP 422 if:
    - Record not found
    - Any of adjusted_bust_cm, adjusted_waist_cm, adjusted_hips_cm is ≤ 0 or > 300

    Requirements: 1.1, 1.3, 1.4
    """
    adjustment: MeasurementAdjustment | None = await db.get(
        MeasurementAdjustment, adjustment_id
    )
    if adjustment is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Ajustement {adjustment_id} introuvable.",
        )

    # Validate each adjusted zone — just check for non-positive values
    for field_name, value in (
        ("adjusted_bust_cm", adjustment.adjusted_bust_cm),
        ("adjusted_waist_cm", adjustment.adjusted_waist_cm),
        ("adjusted_hips_cm", adjustment.adjusted_hips_cm),
    ):
        fval = float(value)
        if fval <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Valeur invalide pour '{field_name}': {fval} cm. "
                    f"La valeur doit être positive."
                ),
            )

    return adjustment


async def _load_model_or_422(
    model_id: uuid.UUID,
    db: AsyncSession,
) -> Model:
    """
    Load Model by PK and verify it is Published.

    Raises HTTP 422 if:
    - Model not found
    - Model status is not Published (includes current status in error)

    Requirements: 1.5, 1.6
    """
    model: Model | None = await db.get(Model, model_id)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Modèle {model_id} introuvable.",
        )

    if model.status != ModelStatusEnum.Published:
        current = model.status.value if hasattr(model.status, "value") else str(model.status)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Le modèle n'est pas publié. "
                f"Statut actuel: '{current}'."
            ),
        )

    # zones are selectin-loaded — already available
    return model


async def _load_fabric_or_422(
    fabric_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[Any, str]:
    """
    Load Fabric + FabricCategory via JOIN and validate availability.

    Returns (row, fabric_property) where fabric_property is the
    reference_rigidity_level from the fabric's category.

    Raises HTTP 422 if:
    - Fabric not found
    - fabric_status ≠ 'available' (includes current status in error)

    Requirements: 1.7, 1.8
    """
    sql = text(
        """
        SELECT
            f.fabric_id,
            f.fabric_name,
            f.fabric_status,
            fc.reference_rigidity_level
        FROM fabrics f
        LEFT JOIN fabric_categories fc ON fc.category_id = f.category_id
        WHERE f.fabric_id = :fabric_id
        """
    )
    result = await db.execute(sql, {"fabric_id": str(fabric_id)})
    row = result.mappings().first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Tissu {fabric_id} introuvable dans le catalogue.",
        )

    if row["fabric_status"] != "available":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Le tissu n'est pas disponible. "
                f"Statut actuel: '{row['fabric_status']}'."
            ),
        )

    fabric_property: str = row["reference_rigidity_level"] or "rigid"
    return row, fabric_property


async def _load_morphology_or_422(
    morphology_id: uuid.UUID,
    db: AsyncSession,
    silhouette_code: str | None = None,
) -> Any:
    """
    Confirm a BodyShape record exists.
    Accepts either a silhouette_code string (e.g. "HOURGLASS") directly,
    or falls back to querying by str(morphology_id) as the code.
    Requirements: 1.9, 1.10
    """
    code_to_check = silhouette_code or str(morphology_id)
    sql = text("SELECT code FROM body_shapes WHERE code = :code")
    result = await db.execute(sql, {"code": code_to_check})
    row = result.mappings().first()

    if row is None:
        # If still not found, try all codes (case-insensitive)
        sql2 = text("SELECT code FROM body_shapes WHERE UPPER(code) = UPPER(:code)")
        result2 = await db.execute(sql2, {"code": code_to_check})
        row = result2.mappings().first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Morphologie '{code_to_check}' introuvable.",
        )

    return row


async def _load_active_rules(
    cut_type: str,
    fabric_property: str,
    db: AsyncSession,
) -> list[RuleRecord]:
    """
    Load the highest-version active CompatibilityRules for a cut/fabric combination.

    Uses version-deduplication SQL: for each zone_id group, keep only the row(s)
    with MAX(version). LEFT JOINs critical_zone to resolve zone_name.

    Returns list[RuleRecord] (may be empty → Indeterminate path).
    Raises HTTP 500 on any DB technical error.

    Requirements: 2.1, 2.5
    """
    sql = text(
        """
        SELECT cr.rule_id,
               cr.zone_id,
               cr.cut_type,
               cr.fabric_property,
               cr.mathematical_condition,
               cr.severity_level,
               cr.explanation_message,
               cr.version,
               COALESCE(cz.zone_name, CAST(cr.zone_id AS TEXT)) AS zone_name
        FROM compatibility_rules cr
        INNER JOIN (
            SELECT zone_id, MAX(version) AS max_version
            FROM compatibility_rules
            WHERE cut_type = :cut_type
              AND fabric_property = :fabric_property
              AND is_active = true
            GROUP BY zone_id
        ) latest ON cr.zone_id = latest.zone_id
               AND cr.version = latest.max_version
        LEFT JOIN critical_zone cz ON cz.zone_id = cr.zone_id
        WHERE cr.cut_type = :cut_type
          AND cr.fabric_property = :fabric_property
          AND cr.is_active = true
        """
    )
    try:
        result = await db.execute(
            sql, {"cut_type": cut_type, "fabric_property": fabric_property}
        )
        rows = result.mappings().all()
    except Exception as exc:
        logger.error(
            "DB error loading active rules (cut_type=%s, fabric_property=%s): %s",
            cut_type, fabric_property, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur technique lors du chargement des règles de compatibilité.",
        ) from exc

    return [
        RuleRecord(
            rule_id=row["rule_id"],
            zone_id=row["zone_id"],
            zone_name=row["zone_name"] or "",
            mathematical_condition=row["mathematical_condition"],
            severity_level=row["severity_level"],
            explanation_message=row["explanation_message"],
            version=row["version"],
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Task 5.2 — Morphology-check, fabric-link-check, verdict-aggregation, persist
# ---------------------------------------------------------------------------


async def _check_morphology_link(
    model_id: uuid.UUID,
    morphology_id: uuid.UUID,
    db: AsyncSession,
) -> str | None:
    """
    Query model_morphology for a suitability_score.

    Returns the suitability_score string or None if no link exists.
    Raises HTTP 500 on DB error.

    Requirements: 4.1–4.5
    """
    sql = text(
        """
        SELECT suitability_score
        FROM model_morphology
        WHERE model_id = :model_id
          AND morphology_id = :morphology_id
        """
    )
    try:
        result = await db.execute(
            sql, {"model_id": str(model_id), "morphology_id": str(morphology_id)}
        )
        row = result.mappings().first()
    except Exception as exc:
        logger.error(
            "DB error checking morphology link (model=%s, morphology=%s): %s",
            model_id, morphology_id, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur technique lors de la vérification de la morphologie.",
        ) from exc

    return row["suitability_score"] if row else None


async def _check_fabric_link(
    model_id: uuid.UUID,
    fabric_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[str | None, RiskZoneDict | None]:
    """
    Query model_fabric for a fabric recommendation link.

    Returns:
    - (None, RiskZoneDict) — fabric not listed → adds a Reserve risk zone
    - ("Accepted", None)   — fabric link exists (no recommendation_level column)

    Requirements: 12.1–12.4
    """
    sql = text(
        """
        SELECT fabric_id
        FROM model_fabric
        WHERE model_id = :model_id
          AND fabric_id = :fabric_id
        """
    )
    try:
        result = await db.execute(
            sql, {"model_id": str(model_id), "fabric_id": str(fabric_id)}
        )
        row = result.mappings().first()
    except Exception as exc:
        logger.error(
            "DB error checking fabric link (model=%s, fabric=%s): %s",
            model_id, fabric_id, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur technique lors de la vérification du tissu.",
        ) from exc

    if row is not None:
        # Fabric is linked; ModelFabric has no recommendation_level column
        return "Accepted", None

    # Fabric not in model's approved list → Reserve risk zone (Req 12.3)
    fabric_risk = RiskZoneDict(
        rule_id=None,
        zone_id=None,
        calculated_variance=0.0,
        localized_verdict="Reserve",
        explanation=(
            "Fabric not listed as compatible with this model by the administrator"
        ),
        rule_version=0,
        warnings=[],
    )
    return None, fabric_risk


def _aggregate_verdict(risk_zones: list[RiskZoneDict]) -> str:
    """
    Compute the global status from a list of risk zones.

    Priority order (Req 5.1):
        Incompatible > Compatible_with_Reservations > Compatible
    """
    if any(rz.localized_verdict == "Incompatible" for rz in risk_zones):
        return "Incompatible"
    if any(rz.localized_verdict == "Reserve" for rz in risk_zones):
        return "Compatible_with_Reservations"
    return "Compatible"


async def _persist_evaluation(
    eval_data: dict,
    risk_zones: list[RiskZoneDict],
    db: AsyncSession,
) -> VerdictEvaluation:
    """
    Persist VerdictEvaluation + all RiskZone rows in a single transaction.

    UUID collision: if IntegrityError on evaluation_id, retry once with a new UUID.
    Rolls back entirely on any failure (Req 7.7, 7.8).

    Requirements: 7.1–7.8
    """
    for attempt in range(2):
        try:
            async with db.begin():
                evaluation = VerdictEvaluation(**eval_data)
                db.add(evaluation)
                await db.flush()  # obtain evaluation_id for FK references

                for rz in risk_zones:
                    db.add(
                        RiskZone(
                            evaluation_id=evaluation.evaluation_id,
                            rule_id=rz.rule_id,
                            zone_id=rz.zone_id,
                            calculated_variance=rz.calculated_variance,
                            localized_verdict=rz.localized_verdict,
                            explanation=rz.explanation,
                            rule_version=rz.rule_version,
                        )
                    )
                # transaction commits on context-manager exit
            return evaluation

        except IntegrityError as exc:
            if attempt == 0 and "evaluation_id" in str(exc).lower():
                # UUID collision — retry once with a fresh UUID (Req 7.6)
                logger.warning("UUID collision on evaluation_id — retrying with new UUID")
                eval_data = {**eval_data, "evaluation_id": uuid.uuid4()}
                continue
            logger.error("Persistence IntegrityError: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur de persistance de l'évaluation (contrainte d'intégrité).",
            ) from exc
        except Exception as exc:
            logger.error("Persistence error: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur lors de la persistance de l'évaluation.",
            ) from exc

    # Should never reach here
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Impossible de persister l'évaluation après deux tentatives.",
    )


# ---------------------------------------------------------------------------
# Task 5.3 + 5.4 — CompatibilityService
# ---------------------------------------------------------------------------


class CompatibilityService:
    """
    Async orchestrator for Module 6 compatibility evaluations and rule administration.

    All methods are @staticmethod — no instance state.
    """

    # ------------------------------------------------------------------
    # Task 5.3 — verify() — 6-phase compatibility pipeline
    # ------------------------------------------------------------------

    @staticmethod
    async def verify(
        request: VerificationRequest,
        user_id: uuid.UUID,
        db: AsyncSession,
    ) -> VerdictEvaluationResponse:
        """
        Run a full compatibility evaluation.

        Phase 1 — Input validation (load all upstream entities)
        Phase 2 — Rule loading (version-deduped active rules)
        Phase 3 — Zone evaluation (pure, no DB)
        Phase 4 — Morphology check
        Phase 5 — Fabric recommendation check
        Phase 6 — Aggregation, invariant check, persist, return

        Requirements: 1.12, 2.3–2.7, 3.1–3.9, 4.1–4.5, 5.1–5.6, 6.1–6.4,
                      7.1–7.8, 11.1–11.4, 12.1–12.4
        """
        # ── Phase 1 — Input Validation ────────────────────────────────
        adjustment = await _load_adjustment_or_422(request.adjustment_id, db)
        model = await _load_model_or_422(request.model_id, db)
        fabric_row, fabric_property = await _load_fabric_or_422(request.fabric_id, db)
        await _load_morphology_or_422(request.morphology_id, db, silhouette_code=request.silhouette_code)

        # ── Phase 2 — Rule Loading ────────────────────────────────────
        cut_type = (
            model.cut_type.value if hasattr(model.cut_type, "value") else str(model.cut_type)
        )
        active_rules = await _load_active_rules(cut_type, fabric_property, db)

        if not active_rules:
            # Indeterminate path — no rules cover this cut/fabric combination
            missing_log = (
                f"Aucune règle active pour cut_type={cut_type}, "
                f"fabric_property={fabric_property}"
            )
            logger.error(
                "Indeterminate evaluation — no rule found",
                extra={
                    "cut_type": cut_type,
                    "fabric_property": fabric_property,
                    "model_id": str(request.model_id),
                    "fabric_id": str(request.fabric_id),
                },
            )
            eval_data = dict(
                evaluation_id=uuid.uuid4(),
                global_status="Indeterminate",
                missing_data_log=missing_log,
                fabric_recommendation=None,
                client_id=request.client_id,
                model_id=request.model_id,
                fabric_id=request.fabric_id,
                measurements_id=request.adjustment_id,
                morphology_id=request.morphology_id,
            )
            evaluation = await _persist_evaluation(eval_data, [], db)
            return VerdictEvaluationResponse.model_validate(evaluation)

        # ── Phase 3 — Zone Evaluation (pure, no DB) ───────────────────
        zone_measurements = {
            "bust": float(adjustment.adjusted_bust_cm),
            "waist": float(adjustment.adjusted_waist_cm),
            "hips": float(adjustment.adjusted_hips_cm),
        }
        critical_zone_ids = [zone.zone_id for zone in model.zones]
        rule_input = RuleInput(
            rules=active_rules,
            zone_measurements=zone_measurements,
            critical_zone_ids=critical_zone_ids,
        )
        risk_zone_dicts: list[RiskZoneDict] = RuleEvaluator().evaluate(rule_input)

        # ── Phase 4 — Morphology Check ────────────────────────────────
        suitability = await _check_morphology_link(
            request.model_id, request.morphology_id, db
        )
        if suitability == "Avoid":
            risk_zone_dicts.append(
                RiskZoneDict(
                    rule_id=None,
                    zone_id=None,
                    calculated_variance=0.0,
                    localized_verdict="Reserve",
                    explanation=(
                        "Cette morphologie est classée 'À éviter' pour ce modèle."
                    ),
                    rule_version=0,
                    warnings=[],
                )
            )

        # ── Phase 5 — Fabric Recommendation Check ─────────────────────
        fabric_recommendation, fabric_risk = await _check_fabric_link(
            request.model_id, request.fabric_id, db
        )
        if fabric_risk is not None:
            risk_zone_dicts.append(fabric_risk)

        # ── Phase 6 — Aggregation, Invariant Check, Persist, Return ──
        global_status = _aggregate_verdict(risk_zone_dicts)

        # Invariant check (Req 5.3): Incompatible status must have ≥ 1 Incompatible zone
        if global_status == "Incompatible":
            incompat_zones = [
                rz for rz in risk_zone_dicts if rz.localized_verdict == "Incompatible"
            ]
            if not incompat_zones:
                logger.error(
                    "Invariant violation: global_status=Incompatible but no "
                    "RiskZone with localized_verdict=Incompatible"
                )
                eval_data = dict(
                    evaluation_id=uuid.uuid4(),
                    global_status="Failed",
                    missing_data_log=(
                        "Invariant violation: Incompatible status but no Incompatible RiskZone"
                    ),
                    fabric_recommendation=None,
                    client_id=request.client_id,
                    model_id=request.model_id,
                    fabric_id=request.fabric_id,
                    measurements_id=request.adjustment_id,
                    morphology_id=request.morphology_id,
                )
                await _persist_evaluation(eval_data, [], db)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Internal invariant violation",
                )

        eval_data = dict(
            evaluation_id=uuid.uuid4(),
            global_status=global_status,
            missing_data_log=None,
            fabric_recommendation=fabric_recommendation,
            client_id=request.client_id,
            model_id=request.model_id,
            fabric_id=request.fabric_id,
            measurements_id=request.adjustment_id,
            morphology_id=request.morphology_id,
        )
        evaluation = await _persist_evaluation(eval_data, risk_zone_dicts, db)
        return VerdictEvaluationResponse.model_validate(evaluation)

    # ------------------------------------------------------------------
    # Task 5.4 — Rule administration methods
    # ------------------------------------------------------------------

    @staticmethod
    async def create_rule(
        body: CompatibilityRuleCreate,
        admin_id: uuid.UUID,
        db: AsyncSession,
    ) -> CompatibilityRuleResponse:
        """
        Create a new CompatibilityRule with version=1.

        Raises HTTP 409 if a duplicate (cut_type, fabric_property, zone_id, is_active)
        unique constraint is violated.

        Requirements: 9.1, 9.6
        """
        rule = CompatibilityRule(
            rule_id=uuid.uuid4(),
            cut_type=body.cut_type,
            fabric_property=body.fabric_property,
            zone_id=body.zone_id,
            mathematical_condition=body.mathematical_condition,
            severity_level=body.severity_level,
            explanation_message=body.explanation_message,
            is_active=body.is_active,
            version=1,
            admin_id=admin_id,
        )
        try:
            async with db.begin():
                db.add(rule)
                await db.flush()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Une règle active avec ce triplet "
                    "(cut_type, fabric_property, zone_id) existe déjà."
                ),
            ) from exc

        return CompatibilityRuleResponse.model_validate(rule)

    @staticmethod
    async def update_rule(
        rule_id: uuid.UUID,
        body: CompatibilityRuleUpdate,
        db: AsyncSession,
    ) -> CompatibilityRuleResponse:
        """
        Update mutable fields of an existing CompatibilityRule and increment version.

        Mutable fields: mathematical_condition, severity_level, explanation_message,
                        is_active.
        Immutable fields: cut_type, fabric_property, zone_id — any attempt to pass
                          them in the body is rejected at the schema level (not in body).

        Raises HTTP 404 if rule_id not found.

        Requirements: 9.2, 9.3, 9.7
        """
        rule: CompatibilityRule | None = await db.get(CompatibilityRule, rule_id)
        if rule is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Règle {rule_id} introuvable.",
            )

        # Apply only fields that were explicitly provided (non-None)
        if body.mathematical_condition is not None:
            rule.mathematical_condition = body.mathematical_condition
        if body.severity_level is not None:
            rule.severity_level = body.severity_level
        if body.explanation_message is not None:
            rule.explanation_message = body.explanation_message
        if body.is_active is not None:
            rule.is_active = body.is_active

        # Increment version on every successful PATCH (Req 9.3)
        rule.version = rule.version + 1

        async with db.begin():
            db.add(rule)
            await db.flush()

        return CompatibilityRuleResponse.model_validate(rule)

    @staticmethod
    async def list_rules(
        db: AsyncSession,
        limit: int = 200,
    ) -> list[CompatibilityRuleResponse]:
        """
        Return all CompatibilityRules (active and inactive), capped at 200 rows.

        Requirements: 9.4
        """
        stmt = select(CompatibilityRule).limit(limit)
        result = await db.execute(stmt)
        rules = result.scalars().all()
        return [CompatibilityRuleResponse.model_validate(r) for r in rules]

    @staticmethod
    async def get_evaluation(
        evaluation_id: uuid.UUID,
        db: AsyncSession,
    ) -> VerdictEvaluationResponse:
        """
        Load a persisted VerdictEvaluation with its selectin-loaded risk_zones.

        Raises HTTP 404 if not found.

        Requirements: 10.4, 10.5
        """
        evaluation: VerdictEvaluation | None = await db.get(
            VerdictEvaluation, evaluation_id
        )
        if evaluation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Évaluation {evaluation_id} introuvable.",
            )
        return VerdictEvaluationResponse.model_validate(evaluation)
