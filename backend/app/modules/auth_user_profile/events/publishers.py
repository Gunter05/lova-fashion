"""
Event producers for the auth_catalogues module.
Publishes: user.authenticated, user.profile_data, user.profile_data.error
"""
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.auth_catalogues.events.bus import EventBus

logger = logging.getLogger(__name__)


async def publish_user_authenticated(
    bus: "EventBus",
    cni: str,
    role: str,
    authenticated_at: datetime | None = None,
) -> None:
    """
    Publish user.authenticated. If bus is unavailable, log and return (Req 2.5, 2.8).
    """
    if authenticated_at is None:
        authenticated_at = datetime.now(timezone.utc)
    try:
        await bus.publish("user.authenticated", {
            "type": "user.authenticated",
            "emitted_at": datetime.now(timezone.utc).isoformat(),
            "cni": cni,
            "role": role,
            "authenticated_at": authenticated_at.isoformat(),
        })
    except Exception as exc:
        logger.warning("Failed to publish user.authenticated for cni=%s: %s", cni, exc)


async def publish_user_profile_data(
    bus: "EventBus",
    cni: str,
    mensurations: list[dict],
) -> None:
    """Publish user.profile_data (Req 11.1, 11.2)."""
    await bus.publish("user.profile_data", {
        "type": "user.profile_data",
        "emitted_at": datetime.now(timezone.utc).isoformat(),
        "cni": cni,
        "mensurations": mensurations,
    })


async def publish_user_profile_data_error(
    bus: "EventBus",
    cni: str,
    reason: str,
) -> None:
    """Publish user.profile_data.error (Req 11.3, 11.4)."""
    await bus.publish("user.profile_data.error", {
        "type": "user.profile_data.error",
        "emitted_at": datetime.now(timezone.utc).isoformat(),
        "cni": cni,
        "reason": reason,
    })
