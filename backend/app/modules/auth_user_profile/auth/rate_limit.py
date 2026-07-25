"""
In-memory rate limiter for login attempts.

Tracks per-email failed login attempts within a rolling 15-minute window.
After 5 consecutive failures, further attempts are blocked until the window expires.

Design reference: Authentication & Security Design — Rate Limiting
Requirement: 2.7

Upgrade path: Replace the in-memory dict with a Redis key for multi-worker deployments.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict

WINDOW_SECONDS: int = 900      # 15 minutes
MAX_FAILURES: int = 5


@dataclass
class _AttemptRecord:
    """Tracks failed login attempts for a single email address."""
    count: int = 0
    window_start: float = field(default_factory=time.monotonic)


class RateLimiter:
    """
    Thread-safe, in-memory rate limiter.

    Usage:
        limiter = RateLimiter()
        # On failed login:
        limiter.record_failure(email)
        # Before login attempt:
        if limiter.is_locked(email):
            raise HTTPException(429, ...)
        # On successful login:
        limiter.reset(email)
    """

    def __init__(self) -> None:
        self._records: Dict[str, _AttemptRecord] = {}
        self._lock = Lock()

    def _get_record(self, email: str) -> _AttemptRecord:
        """Return the attempt record for the email, creating it if absent."""
        if email not in self._records:
            self._records[email] = _AttemptRecord()
        record = self._records[email]
        # Auto-reset if the current window has expired
        elapsed = time.monotonic() - record.window_start
        if elapsed >= WINDOW_SECONDS:
            record.count = 0
            record.window_start = time.monotonic()
        return record

    def record_failure(self, email: str) -> None:
        """
        Increment the failed-attempt counter for the given email.
        If the window has expired, the counter resets before incrementing.
        """
        with self._lock:
            record = self._get_record(email)
            record.count += 1

    def is_locked(self, email: str) -> bool:
        """
        Return True if the email has reached or exceeded MAX_FAILURES
        consecutive failed attempts within the current 15-minute window.
        """
        with self._lock:
            record = self._get_record(email)
            return record.count >= MAX_FAILURES

    def reset(self, email: str) -> None:
        """
        Reset the failure counter for the given email on successful login.
        """
        with self._lock:
            if email in self._records:
                del self._records[email]

    def retry_after(self, email: str) -> int:
        """
        Return the number of seconds remaining in the current lock window.
        Returns 0 if the email is not locked.
        """
        with self._lock:
            if email not in self._records:
                return 0
            record = self._records[email]
            if record.count < MAX_FAILURES:
                return 0
            elapsed = time.monotonic() - record.window_start
            remaining = WINDOW_SECONDS - elapsed
            return max(0, int(remaining))


# Module-level singleton — shared across all requests in a single process
rate_limiter = RateLimiter()
