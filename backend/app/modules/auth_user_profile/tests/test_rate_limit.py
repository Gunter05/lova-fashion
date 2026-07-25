"""
Property-based tests for the in-memory rate limiter.

Feature: auth-user-profile
Property 9: Login Rate-Limiting Enforcement
Validates: Requirements 2.7

Pattern: Error Conditions — every attempt after the 5th failure is rejected
"""
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.modules.auth_user_profile.auth.rate_limit import RateLimiter, MAX_FAILURES, WINDOW_SECONDS


@given(failure_count=st.integers(min_value=MAX_FAILURES, max_value=20))
@settings(max_examples=100)
def test_is_locked_after_max_failures(failure_count: int):
    """
    Feature: auth-user-profile, Property 9: Rate-Limiting Enforcement
    After MAX_FAILURES consecutive failures within the window, is_locked returns True.
    """
    limiter = RateLimiter()
    email = "test@example.com"
    for _ in range(failure_count):
        limiter.record_failure(email)
    assert limiter.is_locked(email) is True, (
        f"Expected is_locked=True after {failure_count} failures"
    )


@given(failure_count=st.integers(min_value=1, max_value=MAX_FAILURES - 1))
@settings(max_examples=100)
def test_not_locked_below_threshold(failure_count: int):
    """
    Feature: auth-user-profile, Property 9: Rate-Limiting Enforcement
    Below MAX_FAILURES, is_locked returns False.
    """
    limiter = RateLimiter()
    email = "below@example.com"
    for _ in range(failure_count):
        limiter.record_failure(email)
    assert limiter.is_locked(email) is False, (
        f"Expected is_locked=False after only {failure_count} failures"
    )


# ── Example-based tests ───────────────────────────────────────────────────────

def test_reset_clears_lock():
    """After reset, a previously locked email is no longer locked."""
    limiter = RateLimiter()
    email = "reset@example.com"
    for _ in range(MAX_FAILURES):
        limiter.record_failure(email)
    assert limiter.is_locked(email) is True
    limiter.reset(email)
    assert limiter.is_locked(email) is False


def test_retry_after_returns_positive_when_locked():
    """retry_after returns a positive integer when email is locked."""
    limiter = RateLimiter()
    email = "retry@example.com"
    for _ in range(MAX_FAILURES):
        limiter.record_failure(email)
    remaining = limiter.retry_after(email)
    assert remaining > 0


def test_retry_after_returns_zero_when_not_locked():
    """retry_after returns 0 for an email with no failures."""
    limiter = RateLimiter()
    assert limiter.retry_after("fresh@example.com") == 0


def test_new_email_not_locked():
    """A brand-new email address is never locked."""
    limiter = RateLimiter()
    assert limiter.is_locked("new@example.com") is False
