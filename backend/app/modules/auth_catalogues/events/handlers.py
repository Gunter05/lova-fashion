"""
Event consumers for the auth_catalogues module.

Handlers registered at application startup:
  - measurements.estimated  → Measurement_Service (from Module 2)
  - report.saved            → Profile_Service (from Module 7)
  - profile_data_request    → Profile_Service (from Module 5)
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth_catalogues.measurement.repository import (
    MensurationRepository,
    UserNotFoundError as MensurationUserNotFoundError,
    DuplicateEventError,
)
from app.modules.auth_catalogues.profile.repository import (
    ProfileRepository,
    UserNotFoundError as ProfileUserNotFoundError,
)
from app.modules.auth_catalogues.events.publishers import (
    publish_user_profile_data,
    publish_user_profile_data_error,
)

if TYPE_CHECKING:
    from app.modules.auth_catalogues.events.bus import EventBus

logger = logging.getLogger(__name__)

# Required fields for the measurements.estimated event
_REQUIRED_MEASUREMENT_FIELDS = [
    "cni",
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

    Req 9.1–9.5
    """
    # 1. Validate required fields
    missing = [f for f in _REQUIRED_MEASUREMENT_FIELDS if f not in payload]
    if missing:
        logger.error(
            "measurements.estimated event missing required fields: %s — payload: %s",
            missing,
            payload,
        )
        return

    cni: str = payload["cni"]
    tp: float = payload["tour_poitrine"]
    tt: float = payload["tour_taille"]
    th: float = payload["tour_hanches"]
    lb: float = payload["longueur_bras"]
    h: float = payload["hauteur"]
    source_timestamp: str = payload["source_timestamp"]

    # 2. Validate measurement values (0, 300]
    invalid_fields = []
    for name, value in [
        ("tour_poitrine", tp),
        ("tour_taille", tt),
        ("tour_hanches", th),
        ("longueur_bras", lb),
        ("hauteur", h),
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
            "measurements.estimated event has invalid measurement values for fields %s "
            "(must be > 0 and <= 300) — cni=%s, payload: %s",
            invalid_fields,
            cni,
            payload,
        )
        return

    # 3. Compute idempotency hash
    source_event_hash = hashlib.sha256(
        f"{cni}{tp}{tt}{th}{lb}{h}{source_timestamp}".encode()
    ).hexdigest()

    repo = MensurationRepository(session)

    # 4. Check for duplicate (pre-flight — race condition guard also in DB)
    if await repo.exists_event_hash(source_event_hash):
        logger.warning(
            "Duplicate measurements.estimated event discarded — cni=%s hash=%s",
            cni,
            source_event_hash,
        )
        return

    # 5. Persist
    try:
        await repo.create_mensuration(
            cni=cni,
            tour_poitrine=float(tp),
            tour_taille=float(tt),
            tour_hanches=float(th),
            longueur_bras=float(lb),
            hauteur=float(h),
            source_event_hash=source_event_hash,
        )
    except MensurationUserNotFoundError:
        logger.error(
            "measurements.estimated event references unknown CNI: %s — record not created.",
            cni,
        )
    except DuplicateEventError:
        # Race condition: another worker processed the same event concurrently
        logger.warning(
            "Duplicate measurements.estimated event (race condition) discarded — cni=%s hash=%s",
            cni,
            source_event_hash,
        )


async def handle_report_saved(
    payload: dict,
    session: AsyncSession,
) -> None:
    """
    Handle a report.saved event from Module 7.

    - Validates the CNI exists.
    - Archives the report reference (idempotent: duplicate (cni, report_id) → skip).

    Req 12.1–12.4
    """
    cni = payload.get("cni")
    report_id = payload.get("report_id")
    date_generation_raw = payload.get("date_generation")

    if not cni or not report_id or not date_generation_raw:
        logger.error(
            "report.saved event missing required fields — payload: %s", payload
        )
        return

    # Parse date_generation
    if isinstance(date_generation_raw, datetime):
        date_generation = date_generation_raw
    else:
        try:
            date_generation = datetime.fromisoformat(str(date_generation_raw))
        except (ValueError, TypeError):
            logger.error(
                "report.saved event has invalid date_generation '%s' — cni=%s",
                date_generation_raw,
                cni,
            )
            return

    repo = ProfileRepository(session)

    # Validate CNI exists
    try:
        await repo.get_user(cni)
    except ProfileUserNotFoundError:
        logger.error(
            "report.saved event references unknown CNI: %s — report not archived.", cni
        )
        return

    # Archive (returns None if duplicate — silently handled per Req 12.4)
    await repo.add_rapport(cni=cni, report_id=report_id, date_generation=date_generation)


async def handle_profile_data_request(
    payload: dict,
    session: AsyncSession,
    bus: "EventBus",
) -> None:
    """
    Handle a profile_data_request event from Module 5.

    - Validates user exists.
    - Retrieves latest measurement.
    - Publishes user.profile_data or user.profile_data.error.

    Req 11.1–11.4
    """
    cni = payload.get("cni")
    if not cni:
        logger.error("profile_data_request event missing cni — payload: %s", payload)
        return

    profile_repo = ProfileRepository(session)
    mensuration_repo = MensurationRepository(session)

    # 1. Validate user exists
    try:
        await profile_repo.get_user(cni)
    except ProfileUserNotFoundError:
        await publish_user_profile_data_error(bus, cni, "user_not_found")
        return

    # 2. Retrieve measurement history (ordered DESC — most recent first)
    mensurations = await mensuration_repo.get_history_for_cni(cni)
    if not mensurations:
        await publish_user_profile_data_error(bus, cni, "no_measurements")
        return

    # 3. Take the most recent (first element, since ordered DESC)
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

    await publish_user_profile_data(bus, cni, [mensuration_dict])


# ── Handler factory functions (for session-bound registration at startup) ─────

def make_measurements_handler(session_factory):
    """
    Factory that wraps handle_measurements_estimated with a fresh DB session.
    Register via: event_bus.subscribe("measurements.estimated", make_measurements_handler(AsyncSessionLocal))
    """
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
    """
    Factory that wraps handle_report_saved with a fresh DB session.
    Register via: event_bus.subscribe("report.saved", make_report_saved_handler(AsyncSessionLocal))
    """
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
    """
    Factory that wraps handle_profile_data_request with a fresh DB session.
    Register via: event_bus.subscribe("profile_data_request", make_profile_data_request_handler(AsyncSessionLocal, event_bus))
    """
    async def handler(payload: dict) -> None:
        async with session_factory() as session:
            try:
                await handle_profile_data_request(payload, session, bus)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    return handler
