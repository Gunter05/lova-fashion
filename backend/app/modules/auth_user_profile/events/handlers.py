"""
Event consumers for the auth_catalogues module.

Handlers registered at application startup:
  - measurements.estimated  → Measurement_Service (from Module 2)
  - report.saved            → Profile_Service (from Module 7)
  - profile_data_request    → Profile_Service (from Module 5)

Note: event payloads use `user_id` (UUID string) — cni removed.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth_user_profile.measurement.repository import (
    MensurationRepository,
    UserNotFoundError as MensurationUserNotFoundError,
    DuplicateEventError,
)
from app.modules.auth_user_profile.profile.repository import (
    ProfileRepository,
    UserNotFoundError as ProfileUserNotFoundError,
)
from app.modules.auth_user_profile.events.publishers import (
    publish_user_profile_data,
    publish_user_profile_data_error,
)

if TYPE_CHECKING:
    from app.modules.auth_user_profile.events.bus import EventBus

logger = logging.getLogger(__name__)

# Required fields for the measurements.estimated event
_REQUIRED_MEASUREMENT_FIELDS = [
    "user_id",
    "tour_poitrine",
    "tour_taille",
    "tour_hanches",
    "longueur_bras",
    "hauteur",
    "source_timestamp",
]


async def handle_measurements_estimated(
    payload: dict,
    session: AsyncSession,
) -> None:
    """
    Handle a measurements.estimated event from Module 2.

    - Validates all required fields are present.
    - Validates all measurement values are in (0, 300].
    - Computes a source_event_hash for idempotency.
    - Persists via MensurationRepository (idempotent: duplicate hash → skip).
    """
    # 1. Validate required fields
    missing = [f for f in _REQUIRED_MEASUREMENT_FIELDS if f not in payload]
    if missing:
        logger.error(
            "measurements.estimated event missing required fields: %s — payload: %s",
            missing, payload,
        )
        return

    user_id: str = payload["user_id"]
    tp: float = payload["tour_poitrine"]
    tt: float = payload["tour_taille"]
    th: float = payload["tour_hanches"]
    lb: float = payload["longueur_bras"]
    h: float  = payload["hauteur"]
    source_timestamp: str = payload["source_timestamp"]

    # 2. Validate measurement values (0, 300]
    invalid_fields = []
    for name, value in [
        ("tour_poitrine", tp), ("tour_taille", tt), ("tour_hanches", th),
        ("longueur_bras", lb), ("hauteur", h),
    ]:
        try:
            val = float(value)
        except (TypeError, ValueError):
            invalid_fields.append(name)
            continue
        if val <= 0 or val > 300:
            invalid_fields.append(name)

    if invalid_fields:
        logger.error(
            "measurements.estimated event has invalid values for %s — user_id=%s",
            invalid_fields, user_id,
        )
        return

    # 3. Compute idempotency hash
    source_event_hash = hashlib.sha256(
        f"{user_id}{tp}{tt}{th}{lb}{h}{source_timestamp}".encode()
    ).hexdigest()

    repo = MensurationRepository(session)

    # 4. Check for duplicate
    if await repo.exists_event_hash(source_event_hash):
        logger.warning(
            "Duplicate measurements.estimated event discarded — user_id=%s hash=%s",
            user_id, source_event_hash,
        )
        return

    # 5. Persist
    try:
        await repo.create_mensuration(
            user_id=user_id,
            tour_poitrine=float(tp),
            tour_taille=float(tt),
            tour_hanches=float(th),
            longueur_bras=float(lb),
            hauteur=float(h),
            source_event_hash=source_event_hash,
        )
    except MensurationUserNotFoundError:
        logger.error(
            "measurements.estimated event references unknown user_id: %s — record not created.",
            user_id,
        )
    except DuplicateEventError:
        logger.warning(
            "Duplicate measurements.estimated event (race condition) — user_id=%s hash=%s",
            user_id, source_event_hash,
        )


async def handle_report_saved(
    payload: dict,
    session: AsyncSession,
) -> None:
    """
    Handle a report.saved event from Module 7.

    - Validates the user_id exists.
    - Archives the report reference (idempotent).
    """
    user_id = payload.get("user_id")
    report_id = payload.get("report_id")
    date_generation_raw = payload.get("date_generation")

    if not user_id or not report_id or not date_generation_raw:
        logger.error("report.saved event missing required fields — payload: %s", payload)
        return

    if isinstance(date_generation_raw, datetime):
        date_generation = date_generation_raw
    else:
        try:
            date_generation = datetime.fromisoformat(str(date_generation_raw))
        except (ValueError, TypeError):
            logger.error(
                "report.saved event has invalid date_generation '%s' — user_id=%s",
                date_generation_raw, user_id,
            )
            return

    repo = ProfileRepository(session)

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        logger.error("report.saved event has invalid user_id format: %s", user_id)
        return

    try:
        await repo.get_user(uid)
    except ProfileUserNotFoundError:
        logger.error(
            "report.saved event references unknown user_id: %s — report not archived.", user_id
        )
        return

    await repo.add_rapport(user_id=uid, report_id=report_id, date_generation=date_generation)


async def handle_profile_data_request(
    payload: dict,
    session: AsyncSession,
    bus: "EventBus",
) -> None:
    """
    Handle a profile_data_request event from Module 5.

    - Validates user exists by user_id.
    - Retrieves latest measurement.
    - Publishes user.profile_data or user.profile_data.error.
    """
    user_id = payload.get("user_id")
    if not user_id:
        logger.error("profile_data_request event missing user_id — payload: %s", payload)
        return

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        logger.error("profile_data_request event has invalid user_id format: %s", user_id)
        return

    profile_repo = ProfileRepository(session)
    mensuration_repo = MensurationRepository(session)

    try:
        await profile_repo.get_user(uid)
    except ProfileUserNotFoundError:
        await publish_user_profile_data_error(bus, user_id, "user_not_found")
        return

    mensurations = await mensuration_repo.get_history_for_user(user_id)
    if not mensurations:
        await publish_user_profile_data_error(bus, user_id, "no_measurements")
        return

    latest = mensurations[0]
    mensuration_dict = {
        "id_mesure": latest.id_mesure,
        "tour_poitrine": float(latest.tour_poitrine),
        "tour_taille": float(latest.tour_taille),
        "tour_hanches": float(latest.tour_hanches),
        "longueur_bras": float(latest.longueur_bras),
        "hauteur": float(latest.hauteur),
        "date_mensuration": (
            latest.date_mensuration.isoformat()
            if isinstance(latest.date_mensuration, datetime)
            else str(latest.date_mensuration)
        ),
    }

    await publish_user_profile_data(bus, user_id, [mensuration_dict])


# ── Handler factory functions ──────────────────────────────────────────────────

def make_measurements_handler(session_factory):
    """Factory wrapping handle_measurements_estimated with a fresh DB session."""
    async def handler(payload: dict) -> None:
        async with session_factory() as session:
            try:
                await handle_measurements_estimated(payload, session)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    return handler


def make_report_saved_handler(session_factory):
    """Factory wrapping handle_report_saved with a fresh DB session."""
    async def handler(payload: dict) -> None:
        async with session_factory() as session:
            try:
                await handle_report_saved(payload, session)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    return handler


def make_profile_data_request_handler(session_factory, bus):
    """Factory wrapping handle_profile_data_request with a fresh DB session."""
    async def handler(payload: dict) -> None:
        async with session_factory() as session:
            try:
                await handle_profile_data_request(payload, session, bus)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    return handler
