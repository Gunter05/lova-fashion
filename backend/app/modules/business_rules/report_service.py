"""
Service layer for Module 7 — Final Result & Report (Synthesis).

Provides:
  - build_display_hints()   — pure function, maps verdict → display_hints
  - ReportCreationError     — typed domain exception for guard failures
  - ReportService           — orchestration + DB I/O for all report operations

Design reference: Components and Interfaces §Service Layer
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.business_rules.models import MeasurementAdjustment
from app.modules.business_rules.report_models import RapportMesure
from app.modules.business_rules.report_schemas import (
    AdjustedMeasurementsSnapshot,
    CompatibilityEvaluatedEvent,
    DisplayHints,
    IncompatibleZoneItem,
    ReportSummary,
)

logger = logging.getLogger(__name__)

# ── Verdict → colour mapping ──────────────────────────────────────────────────
_VERDICT_COLOR: dict[str, str] = {
    "compatible":         "green",
    "minor_adjustments":  "orange",
    "incompatible":       "red",
}


# ── Domain exception ──────────────────────────────────────────────────────────

class ReportCreationError(Exception):
    """
    Raised by service helpers when an upstream data guard fails.
    The event handler catches this exception, logs the message as ERROR,
    and silently discards the event (no DB write).
    """
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# ── Pure helper ───────────────────────────────────────────────────────────────

def build_display_hints(
    verdict: str,
    incompatible_zones: Optional[list[IncompatibleZoneItem]],
) -> DisplayHints:
    """
    Derive frontend display hints from the verdict and optional zone list.

    - "compatible"        → green, highlight_zones=[]
    - "minor_adjustments" → orange, highlight_zones=[]
    - "incompatible"      → red, highlight_zones=[<zone names>]

    This function is pure (no DB access) and is called at read time on every
    API response. display_hints is NOT stored in the database.

    Req 3 AC1–3 · Design §Correctness Properties 1–3
    """
    color = _VERDICT_COLOR.get(verdict, "red")
    zones: list[str] = []
    if verdict == "incompatible" and incompatible_zones:
        zones = [item.zone for item in incompatible_zones]
    return DisplayHints(verdict_color=color, highlight_zones=zones)  # type: ignore[arg-type]


# ── Private guard helpers ─────────────────────────────────────────────────────

async def _assert_user_exists(user_id: uuid.UUID, db: AsyncSession) -> None:
    """Raise ReportCreationError if no user with the given user_id exists."""
    from sqlalchemy import text
    result = await db.execute(text("SELECT id FROM users WHERE id = :user_id"), {"user_id": str(user_id)})
    if result.scalar_one_or_none() is None:
        raise ReportCreationError(
            f"Module 7: user_id={user_id!r} not found in users table."
        )


async def _load_adjustment_or_raise(
    adjustment_id: uuid.UUID,
    db: AsyncSession,
) -> MeasurementAdjustment:
    """Load MeasurementAdjustment by PK; raise ReportCreationError if missing. Req 2 AC2"""
    from sqlalchemy import text as _text
    result = await db.execute(
        _text(
            "SELECT id, adjusted_bust_cm, adjusted_waist_cm, adjusted_hips_cm, "
            "bust_ease_cm, waist_ease_cm, hips_ease_cm, ease_source "
            "FROM measurement_adjustments WHERE id = :aid"
        ),
        {"aid": str(adjustment_id)},
    )
    row = result.fetchone()
    if row is None:
        raise ReportCreationError(
            f"Module 7: adjustment_id={adjustment_id!r} not found "
            f"in measurement_adjustments."
        )
    # Return a lightweight mock-like namespace so _validate_measurements and
    # _build_snapshot can access the fields as attributes
    from types import SimpleNamespace
    return SimpleNamespace(
        id=adjustment_id,
        adjusted_bust_cm=row.adjusted_bust_cm,
        adjusted_waist_cm=row.adjusted_waist_cm,
        adjusted_hips_cm=row.adjusted_hips_cm,
        bust_ease_cm=row.bust_ease_cm,
        waist_ease_cm=row.waist_ease_cm,
        hips_ease_cm=row.hips_ease_cm,
        ease_source=row.ease_source,
    )  # type: ignore[return-value]


def _validate_measurements(adjustment: MeasurementAdjustment) -> None:
    """
    Raise ReportCreationError if any adjusted measurement value is negative or NULL.
    Req 2 AC3 · Design §Correctness Property 5
    """
    checks = [
        ("adjusted_bust_cm",  adjustment.adjusted_bust_cm),
        ("adjusted_waist_cm", adjustment.adjusted_waist_cm),
        ("adjusted_hips_cm",  adjustment.adjusted_hips_cm),
    ]
    for field_name, value in checks:
        if value is None:
            raise ReportCreationError(
                f"Module 7: corrupt measurement in adjustment_id="
                f"{adjustment.id!r} — zone={field_name!r} value=NULL."
            )
        if float(value) < 0:
            raise ReportCreationError(
                f"Module 7: corrupt measurement in adjustment_id="
                f"{adjustment.id!r} — zone={field_name!r} value={value}."
            )


async def _assert_fabric_exists(fabric_id: uuid.UUID, db: AsyncSession) -> None:
    """Raise ReportCreationError if no fabric with the given ID exists. Req 4 AC1"""
    from sqlalchemy import text
    result = await db.execute(
        text("SELECT fabric_id FROM fabrics WHERE fabric_id = :fid"),
        {"fid": str(fabric_id)},
    )
    if result.scalar_one_or_none() is None:
        raise ReportCreationError(
            f"Module 7: fabric_id={fabric_id!r} not found in fabrics table."
        )


async def _assert_model_exists(model_id: uuid.UUID, db: AsyncSession) -> None:
    """Raise ReportCreationError if no garment model with the given ID exists. Req 4 AC2"""
    from sqlalchemy import text
    result = await db.execute(
        text("SELECT model_id FROM models WHERE model_id = :mid"),
        {"mid": str(model_id)},
    )
    if result.scalar_one_or_none() is None:
        raise ReportCreationError(
            f"Module 7: model_id={model_id!r} not found in models table."
        )


def _build_snapshot(adjustment: MeasurementAdjustment) -> dict:
    """
    Build the 7-field JSON snapshot dict from the ORM adjustment object.
    This snapshot is stored immutably in rapport_mesure.adjusted_measurements.
    Req 2 AC1 · Req 1 AC4
    """
    return AdjustedMeasurementsSnapshot(
        adjusted_bust_cm=float(adjustment.adjusted_bust_cm),
        adjusted_waist_cm=float(adjustment.adjusted_waist_cm),
        adjusted_hips_cm=float(adjustment.adjusted_hips_cm),
        bust_ease_cm=float(adjustment.bust_ease_cm),
        waist_ease_cm=float(adjustment.waist_ease_cm),
        hips_ease_cm=float(adjustment.hips_ease_cm),
        ease_source=str(adjustment.ease_source),
    ).model_dump()


async def _load_report_or_404(report_id: uuid.UUID, db: AsyncSession) -> RapportMesure:
    """Load RapportMesure by PK; raise HTTP 404 if missing. Req 5 AC2"""
    from sqlalchemy import text as _text
    import json as _json
    result = await db.execute(
        _text("SELECT * FROM rapport_mesure WHERE id_report = :rid"),
        {"rid": str(report_id)},
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report {report_id} not found.",
        )
    # Reconstruct a RapportMesure-compatible namespace from the raw row
    from types import SimpleNamespace
    # adjusted_measurements may be a JSON string in SQLite
    adj_meas = row.adjusted_measurements
    if isinstance(adj_meas, str):
        adj_meas = _json.loads(adj_meas)
    incompatible = row.incompatible_zones
    if isinstance(incompatible, str):
        try:
            incompatible = _json.loads(incompatible)
        except Exception:
            incompatible = None
    return SimpleNamespace(
        id_report=uuid.UUID(row.id_report) if isinstance(row.id_report, str) else row.id_report,
        user_id=uuid.UUID(row.user_id) if isinstance(row.user_id, str) else row.user_id,
        adjustment_id=uuid.UUID(row.adjustment_id) if isinstance(row.adjustment_id, str) else row.adjustment_id,
        fabric_id=uuid.UUID(row.fabric_id) if isinstance(row.fabric_id, str) else row.fabric_id,
        model_id=uuid.UUID(row.model_id) if isinstance(row.model_id, str) else row.model_id,
        verdict=row.verdict,
        advice=row.advice,
        adjusted_measurements=adj_meas,
        incompatible_zones=incompatible,
        generated_at=row.generated_at if isinstance(row.generated_at, datetime) else datetime.fromisoformat(str(row.generated_at)),
    )  # type: ignore[return-value]


async def _query_reports_by_user_id(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[RapportMesure]:
    """SELECT all reports for a user_id ordered by generated_at DESC."""
    import json as _json
    from sqlalchemy import text as _text
    result = await db.execute(
        _text(
            "SELECT * FROM rapport_mesure WHERE user_id = :user_id "
            "ORDER BY generated_at DESC"
        ),
        {"user_id": str(user_id)},
    )
    rows = result.fetchall()
    from types import SimpleNamespace
    reports = []
    for row in rows:
        adj_meas = row.adjusted_measurements
        if isinstance(adj_meas, str):
            adj_meas = _json.loads(adj_meas)
        incompatible = row.incompatible_zones
        if isinstance(incompatible, str):
            try:
                incompatible = _json.loads(incompatible)
            except Exception:
                incompatible = None
        gen_at = row.generated_at
        if isinstance(gen_at, str):
            gen_at = datetime.fromisoformat(gen_at)
        reports.append(SimpleNamespace(
            id_report=uuid.UUID(row.id_report) if isinstance(row.id_report, str) else row.id_report,
            user_id=uuid.UUID(row.user_id) if isinstance(row.user_id, str) else row.user_id,
            adjustment_id=uuid.UUID(row.adjustment_id) if isinstance(row.adjustment_id, str) else row.adjustment_id,
            fabric_id=uuid.UUID(row.fabric_id) if isinstance(row.fabric_id, str) else row.fabric_id,
            model_id=uuid.UUID(row.model_id) if isinstance(row.model_id, str) else row.model_id,
            verdict=row.verdict,
            advice=row.advice,
            adjusted_measurements=adj_meas,
            incompatible_zones=incompatible,
            generated_at=gen_at,
        ))
    return reports  # type: ignore[return-value]


# ── ReportService ─────────────────────────────────────────────────────────────

class ReportService:
    """
    Orchestrates all Module 7 DB operations.

    Methods:
      create_report_from_event  — event-driven report creation (always INSERT)
      get_report                — retrieve one report with access control
      list_reports_for_client   — history list for the authenticated client
      list_reports_for_client_as_tailor — history list accessible by Tailor/Admin
    """

    # ── Report creation ───────────────────────────────────────────────────────

    async def create_report_from_event(
        self,
        event: CompatibilityEvaluatedEvent,
        db: AsyncSession,
    ) -> RapportMesure:
        """
        Execute five upstream guards, snapshot measurements, INSERT a new
        RapportMesure row, commit, and return the ORM object.

        Guards run in this order (fail-fast):
          1. User exists
          2. adjustment_id exists
          3. Adjusted measurements are non-negative
          4. fabric_id exists
          5. model_id exists

        Creation is always INSERT — never UPSERT (immutability, Req 8 AC2).

        Raises ReportCreationError on any guard failure (caller logs + discards).
        Req 1 AC1, AC4–5 · Req 2 · Req 3 AC4 · Req 4 AC1–3 · Req 8 AC2
        """
        user_uuid = uuid.UUID(event.user_id) if isinstance(event.user_id, str) else event.user_id
        # Guard 1: user exists
        await _assert_user_exists(user_uuid, db)

        # Guard 2: adjustment exists
        adjustment = await _load_adjustment_or_raise(event.adjustment_id, db)

        # Guard 3: measurements are valid (non-negative, non-NULL)
        _validate_measurements(adjustment)

        # Guard 4: fabric exists
        await _assert_fabric_exists(event.fabric_id, db)

        # Guard 5: model exists
        await _assert_model_exists(event.model_id, db)

        # Build the immutable snapshot
        snapshot = _build_snapshot(adjustment)

        # Persist incompatible_zones only when verdict is "incompatible"
        zones_data = None
        if event.verdict == "incompatible" and event.incompatible_zones:
            zones_data = [z.model_dump() for z in event.incompatible_zones]

        # BUILD and INSERT — always new row, never overwrite
        import json as _json
        from sqlalchemy import text as _text
        from datetime import timezone as _tz

        new_id = uuid.uuid4()
        zones_json = _json.dumps(zones_data) if zones_data is not None else None
        snapshot_json = _json.dumps(snapshot)

        await db.execute(_text("""
            INSERT INTO rapport_mesure
                (id_report, user_id, adjustment_id, fabric_id, model_id,
                 verdict, adjusted_measurements, advice, incompatible_zones,
                 generated_at)
            VALUES
                (:id_report, :user_id, :adjustment_id, :fabric_id, :model_id,
                 :verdict, :adjusted_measurements, :advice, :incompatible_zones,
                 CURRENT_TIMESTAMP)
        """), {
            "id_report":             str(new_id),
            "user_id":               str(user_uuid),
            "adjustment_id":         str(event.adjustment_id),
            "fabric_id":             str(event.fabric_id),
            "model_id":              str(event.model_id),
            "verdict":               event.verdict,
            "adjusted_measurements": snapshot_json,
            "advice":                event.advice,
            "incompatible_zones":    zones_json,
        })

        # Return a lightweight namespace for the caller to use
        from types import SimpleNamespace
        now = datetime.now(_tz.utc)
        return SimpleNamespace(
            id_report=new_id,
            user_id=user_uuid,
            adjustment_id=event.adjustment_id,
            fabric_id=event.fabric_id,
            model_id=event.model_id,
            verdict=event.verdict,
            advice=event.advice,
            adjusted_measurements=snapshot,
            incompatible_zones=zones_data,
            generated_at=now,
        )  # type: ignore[return-value]

    # ── Report retrieval ──────────────────────────────────────────────────────

    async def get_report(
        self,
        report_id: uuid.UUID,
        caller_id: str,
        caller_role: str,
        db: AsyncSession,
    ) -> RapportMesure:
        """
        Load a report by PK and enforce access control.

        - Client: can only retrieve their own report (user_id must match).
        - Tailor / Admin: unrestricted access to any report.

        Raises HTTP 404 if not found, HTTP 403 if caller is a client
        whose user_id does not match the report's user_id.

        Req 5 AC1–5
        """
        report = await _load_report_or_404(report_id, db)

        # Clients may only access their own report
        if caller_role.lower() in ("client",):
            if str(report.user_id) != str(caller_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to access this report.",
                )

        return report

    # ── History lists ─────────────────────────────────────────────────────────

    async def list_all_reports(
        self,
        db: AsyncSession,
    ) -> list[RapportMesure]:
        """
        Return all reports, ordered newest first.
        """
        import json as _json
        from sqlalchemy import text as _text
        from types import SimpleNamespace
        result = await db.execute(
            _text("SELECT * FROM rapport_mesure ORDER BY generated_at DESC")
        )
        rows = result.fetchall()
        reports = []
        for row in rows:
            adj_meas = row.adjusted_measurements
            if isinstance(adj_meas, str):
                adj_meas = _json.loads(adj_meas)
            incompatible = row.incompatible_zones
            if isinstance(incompatible, str):
                try:
                    incompatible = _json.loads(incompatible)
                except Exception:
                    incompatible = None
            gen_at = row.generated_at
            if isinstance(gen_at, str):
                gen_at = datetime.fromisoformat(gen_at)
            reports.append(SimpleNamespace(
                id_report=uuid.UUID(row.id_report) if isinstance(row.id_report, str) else row.id_report,
                user_id=uuid.UUID(row.user_id) if isinstance(row.user_id, str) else row.user_id,
                adjustment_id=uuid.UUID(row.adjustment_id) if isinstance(row.adjustment_id, str) else row.adjustment_id,
                fabric_id=uuid.UUID(row.fabric_id) if isinstance(row.fabric_id, str) else row.fabric_id,
                model_id=uuid.UUID(row.model_id) if isinstance(row.model_id, str) else row.model_id,
                verdict=row.verdict,
                advice=row.advice,
                adjusted_measurements=adj_meas,
                incompatible_zones=incompatible,
                generated_at=gen_at,
            ))
        return reports

    async def list_reports_for_client(
        self,
        user_id: str,
        db: AsyncSession,
    ) -> list[RapportMesure]:
        """
        Return all reports for the given user_id, ordered newest first.
        Returns an empty list when no reports exist (Req 6 AC2).
        Req 6 AC1–2
        """
        user_uuid = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
        return await _query_reports_by_user_id(user_uuid, db)

    async def list_reports_for_client_as_tailor(
        self,
        target_user_id: str,
        db: AsyncSession,
    ) -> list[RapportMesure]:
        """
        Return all reports for the target user_id (Tailor/Admin access).
        Raises HTTP 404 if the target user does not exist.
        Req 7 AC1–4
        """
        target_uuid = uuid.UUID(target_user_id) if isinstance(target_user_id, str) else target_user_id
        try:
            await _assert_user_exists(target_uuid, db)
        except ReportCreationError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            )
        return await _query_reports_by_user_id(target_uuid, db)

    # ── Helper: build ReportSummary list ─────────────────────────────────────

    @staticmethod
    def to_summary_list(reports: list[RapportMesure]) -> list[ReportSummary]:
        """Convert ORM objects to ReportSummary, computing verdict_color inline."""
        summaries = []
        for r in reports:
            color = _VERDICT_COLOR.get(r.verdict, "red")
            summaries.append(
                ReportSummary(
                    report_id=r.id_report,
                    verdict=r.verdict,           # type: ignore[arg-type]
                    verdict_color=color,          # type: ignore[arg-type]
                    fabric_id=r.fabric_id,
                    model_id=r.model_id,
                    generated_at=r.generated_at,
                )
            )
        return summaries
