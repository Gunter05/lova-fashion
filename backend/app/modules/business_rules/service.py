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

    if session.user_id != user_id:
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
        LEFT JOIN fabric_categories fc ON fc.id = f.category_id
        WHERE f.id = :fabric_id
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
