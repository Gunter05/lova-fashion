"""
In-process Event_Bus: publish/subscribe registry.
MVP implementation — swap bus adapter to migrate to external broker without changing contracts.
"""
import asyncio
import logging
from collections import defaultdict
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Callable[..., Awaitable]) -> None:
        """Register *handler* to be called when *event_type* is published."""
        self._handlers[event_type].append(handler)

    async def publish(self, event_type: str, payload: dict) -> None:
        """
        Deliver *payload* to all handlers subscribed to *event_type*.
        Handler exceptions are logged but never re-raised (non-blocking for caller).
        """
        for handler in self._handlers.get(event_type, []):
            try:
                await handler(payload)
            except Exception as exc:
                logger.error(
                    "EventBus handler failed for event '%s': %s",
                    event_type, exc,
                    exc_info=True,
                )


# Module-level singleton — shared across all publishers and handlers in a single process
event_bus = EventBus()
