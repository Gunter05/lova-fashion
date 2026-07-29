"""
EventBus handler for Module 7 — Final Result & Report (Synthesis).

Subscribes to `compatibility.evaluated` on the shared in-process EventBus singleton.
On receipt, validates the payload, creates an immutable RapportMesure record,
and publishes `report.saved` to Module 1's archival handler (fire-and-forget).

Design reference: Components and Interfaces §Event Handler
Req 1 AC1–2 · Req 4 AC4 · Req 9 AC1–3
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from pydantic import ValidationError

from app.modules.business_rules.report_schemas import (
    CompatibilityEvaluatedEvent,
    ReportSavedEvent,
)
from app.modules.business_rules.report_service import ReportCreationError, ReportService

logger = logging.getLogger(__name__)


def make_compatibility_evaluated_handler(session_factory):
    """
    Factory that returns a coroutine subscribed to the `compatibility.evaluated`
    EventBus event.

    Each delivery opens its own AsyncSession so that:
    - DB errors are isolated from other concurrent event deliveries.
    - The session is committed on success and rolled back on any exception.

    The `report.saved` EventBus publish is fire-and-forget: an exception from
    the bus is caught, logged as WARNING, and never propagated (Req 4 AC4).

    Usage in main.py lifespan::

        event_bus.subscribe(
            "compatibility.evaluated",
            make_compatibility_evaluated_handler(AsyncSessionLocal),
        )

    Req 1 AC1–2 · Req 4 AC4 · Req 9 AC1–3
    """
    service = ReportService()

    async def handle_compatibility_evaluated(payload: dict) -> None:
        # ── Step 1: Parse & validate the event payload ────────────────────────
        try:
            event = CompatibilityEvaluatedEvent.model_validate(payload)
        except (ValidationError, Exception) as exc:
            logger.error(
                "Module 7: invalid compatibility.evaluated payload — %s | payload=%s",
                exc,
                payload,
            )
            return  # discard malformed event; no DB write

        # ── Step 2: Create the report ─────────────────────────────────────────
        report = None
        async with session_factory() as db:
            try:
                report = await service.create_report_from_event(event, db)
                await db.commit()
                await db.refresh(report)
                logger.info(
                    "Module 7: RapportMesure created — id=%s user_id=%s verdict=%s",
                    report.id_report,
                    event.user_id,
                    event.verdict,
                )
            except ReportCreationError as exc:
                await db.rollback()
                logger.error("%s", exc.message)
                return  # upstream data missing/corrupt; discard
            except Exception as exc:
                await db.rollback()
                logger.error(
                    "Module 7: unexpected error creating report for user_id=%s — %s",
                    event.user_id,
                    exc,
                    exc_info=True,
                )
                return

        # ── Step 3: Publish report.saved (fire-and-forget) ────────────────────
        # Report is already committed; a publish failure must never roll it back.
        try:
            from app.modules.auth_user_profile.events.bus import event_bus

            saved_event = ReportSavedEvent(
                user_id=event.user_id,
                report_id=str(report.id_report),
                date_generation=report.generated_at.astimezone(timezone.utc).isoformat(),
            )
            await event_bus.publish("report.saved", saved_event.model_dump())
            logger.info(
                "Module 7: report.saved published — report_id=%s user_id=%s",
                saved_event.report_id,
                saved_event.user_id,
            )
        except Exception as exc:
            logger.warning(
                "Module 7: failed to publish report.saved for report_id=%s — %s",
                str(report.id_report) if report else "unknown",
                exc,
            )
            # Do NOT re-raise — the DB record is already committed (Req 9 AC3)

    return handle_compatibility_evaluated
