"""
Property-based tests for security.py — bcrypt password hashing.

Feature: auth-user-profile
Property 1: Password Hashing — Irreversibility and Round-Trip Verify
Validates: Requirements 1.10, 2.1

Pattern: Round-Trip (verify is the non-strict inverse of hash)
"""
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.modules.auth_user_profile.auth.security import hash_password, verify_password


# ── Strategy: passwords without NULL bytes (bcrypt limitation) ────────────────
# bcrypt rejects passwords containing NULL bytes (\x00), so we filter them out.
# Also, bcrypt hashing with cost factor 12 is slow (200-1200ms), so we increase
# the deadline to 2000ms to avoid spurious deadline failures.

password_strategy = st.text(min_size=8).filter(lambda p: '\x00' not in p)


# ── Property 1: Password Hashing — Irreversibility and Round-Trip Verify ──────

@given(password=password_strategy)
@settings(max_examples=100, deadline=2000)
def test_hash_is_never_equal_to_plaintext(password: str):
    """
    Feature: auth-user-profile, Property 1: Password Hashing — Irreversibility
    h(p) != p for all passwords of length >= 8.
    """
    hashed = hash_password(password)
    assert hashed != password, (
        f"hash_password returned the plaintext unchanged for password of length {len(password)}"
    )


@given(password=password_strategy)
@settings(max_examples=100, deadline=2000)
def test_verify_password_round_trip(password: str):
    """
    Feature: auth-user-profile, Property 1: Password Hashing — Round-Trip Verify
    verify(p, hash(p)) == True for all passwords of length >= 8.
    """
    hashed = hash_password(password)
    assert verify_password(password, hashed) is True, (
        f"verify_password returned False for password that was just hashed"
    )


@given(
    password1=password_strategy,
    password2=password_strategy,
)
@settings(max_examples=100, deadline=2000)
def test_different_passwords_do_not_cross_verify(password1: str, password2: str):
    """
    Feature: auth-user-profile, Property 1: Password Hashing — Irreversibility
    p1 != p2 => verify(p1, hash(p2)) == False.
    """
    assume(password1 != password2)
    hashed_p2 = hash_password(password2)
    assert verify_password(password1, hashed_p2) is False, (
        f"verify_password returned True for a different password"
    )


# ── Example-based sanity checks ───────────────────────────────────────────────

def test_hash_is_bcrypt_format():
    """Hashed password should start with bcrypt identifier $2b$."""
    hashed = hash_password("mypassword123")
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$"), (
        f"Expected bcrypt hash format, got: {hashed[:10]}"
    )


def test_verify_wrong_password_returns_false():
    hashed = hash_password("correct-password")
    assert verify_password("wrong-password", hashed) is False


def test_verify_correct_password_returns_true():
    hashed = hash_password("correct-password")
    assert verify_password("correct-password", hashed) is True
