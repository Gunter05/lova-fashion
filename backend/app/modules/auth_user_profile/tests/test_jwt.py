"""
Property-based tests for JWT issuance and decoding.

Feature: auth-user-profile
Property 3: JWT Encode/Decode Round-Trip
Validates: Requirements 2.1, 2.2, 4.2

Pattern: Round-Trip (decode is the inverse of issue)
"""
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.modules.auth_user_profile.auth.security import (
    issue_token,
    decode_token,
    JWT_EXPIRY_SECONDS,
)

VALID_ROLES = ["Client", "Tailor", "Admin"]
USER_ID_STRATEGY = st.uuids().map(str)


@given(
    user_id=USER_ID_STRATEGY,
    role=st.sampled_from(VALID_ROLES),
)
@settings(max_examples=100)
def test_jwt_round_trip_user_id(user_id: str, role: str):
    """
    Feature: auth-user-profile, Property 3: JWT Encode/Decode Round-Trip
    decode(issue(user_id, role)).user_id == user_id for all valid user_id/role pairs.
    """
    token = issue_token(user_id=user_id, role=role)
    claims = decode_token(token)
    assert claims["user_id"] == user_id, f"Expected user_id={user_id}, got {claims['user_id']}"


@given(
    user_id=USER_ID_STRATEGY,
    role=st.sampled_from(VALID_ROLES),
)
@settings(max_examples=100)
def test_jwt_round_trip_role(user_id: str, role: str):
    """
    Feature: auth-user-profile, Property 3: JWT Encode/Decode Round-Trip
    decode(issue(user_id, role)).role == role for all valid pairs.
    """
    token = issue_token(user_id=user_id, role=role)
    claims = decode_token(token)
    assert claims["role"] == role, f"Expected role={role}, got {claims['role']}"


@given(
    user_id=USER_ID_STRATEGY,
    role=st.sampled_from(VALID_ROLES),
)
@settings(max_examples=100)
def test_jwt_expiry_is_exactly_24h(user_id: str, role: str):
    """
    Feature: auth-user-profile, Property 3: JWT Encode/Decode Round-Trip
    exp - iat == 86400 (exactly 24 hours) for all issued tokens.
    """
    token = issue_token(user_id=user_id, role=role)
    claims = decode_token(token)
    assert claims["exp"] - claims["iat"] == JWT_EXPIRY_SECONDS, (
        f"Expected exp-iat={JWT_EXPIRY_SECONDS}, got {claims['exp'] - claims['iat']}"
    )


# ── Example-based sanity checks ───────────────────────────────────────────────

def test_jwt_contains_jti():
    """Issued JWT must contain a jti claim (required for denylist)."""
    token = issue_token(user_id="00000000-0000-0000-0000-000000000001", role="Client")
    claims = decode_token(token)
    assert "jti" in claims
    assert len(claims["jti"]) > 0


def test_jwt_contains_iss():
    """Issued JWT must contain iss claim matching JWT_ISSUER."""
    from app.modules.auth_user_profile.auth.security import JWT_ISSUER
    token = issue_token(user_id="00000000-0000-0000-0000-000000000001", role="Client")
    claims = decode_token(token)
    assert claims["iss"] == JWT_ISSUER


def test_decode_tampered_token_raises():
    """A tampered token must raise TokenInvalidError."""
    from app.modules.auth_user_profile.auth.security import TokenInvalidError
    with pytest.raises(TokenInvalidError):
        decode_token("not.a.valid.jwt")
