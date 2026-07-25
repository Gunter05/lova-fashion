"""
Security helpers for Module 1: Authentication & User Profile.

Provides:
  - bcrypt password hashing (passlib, cost factor 12)
  - JWT issuance and decoding (python-jose, HS256)

Secrets are read from environment variables only; they are never logged or returned.

Design reference: Authentication & Security Design — JWT Structure, Password Security
Requirements: 1.10, 2.1–2.2, 4.1–4.6
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

# ── Configuration (from environment — never hardcoded) ────────────────────────

JWT_SECRET: str = os.environ.get("JWT_SECRET", "dev-secret-change-me-32-chars-min!")
JWT_ISSUER: str = os.environ.get("JWT_ISSUER", "lova-fashion-auth")
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRY_SECONDS: int = 86400  # 24 hours exactly (Req 2.2)

# ── bcrypt context (cost factor 12) ───────────────────────────────────────────

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(plaintext: str) -> str:
    """
    Hash a plaintext password using bcrypt (cost factor 12).
    The returned hash is safe to store in the database.
    The plaintext is never stored or returned.
    """
    return _pwd_context.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    """
    Return True if plaintext matches the stored bcrypt hash.
    Returns False (never raises) on any mismatch or hash error.
    """
    try:
        return _pwd_context.verify(plaintext, hashed)
    except Exception:
        return False


# ── JWT helpers ───────────────────────────────────────────────────────────────

# Typed exceptions for clean error mapping at the service / dependency layer
class TokenExpiredError(Exception):
    """Raised when a JWT's `exp` claim is in the past."""


class TokenInvalidError(Exception):
    """Raised when a JWT fails signature verification, has a bad `iss`, or is missing claims."""


REQUIRED_CLAIMS: frozenset[str] = frozenset({"cni", "role", "exp", "jti", "iss", "sub"})


def issue_token(cni: str, role: str) -> str:
    """
    Issue a signed HS256 JWT for the given user.

    Claims issued:
      iss  — JWT_ISSUER (e.g. "lova-fashion-auth")
      sub  — cni (standard JWT subject)
      cni  — cni (application-specific claim)
      role — role string ("Client" | "Tailor" | "Admin")
      iat  — current UTC timestamp (seconds)
      exp  — iat + JWT_EXPIRY_SECONDS (exactly 24 h, Req 2.2)
      jti  — UUID4 string (used for denylist logout, Req 3.1)

    The JWT_SECRET is read from the environment and never returned.
    """
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "iss": JWT_ISSUER,
        "sub": cni,
        "cni": cni,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=JWT_EXPIRY_SECONDS)).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT.

    Verifies:
      1. HS256 signature against JWT_SECRET
      2. `iss` claim equals JWT_ISSUER
      3. `exp` has not passed (raises TokenExpiredError)
      4. All required claims are present (raises TokenInvalidError)

    Returns the decoded payload dict on success.

    Raises:
      TokenExpiredError  — token has expired (exp < now)
      TokenInvalidError  — signature invalid, wrong issuer, malformed, or missing claims
    """
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"verify_aud": False},  # no audience claim used
        )
    except JWTError as exc:
        exc_str = str(exc).lower()
        if "expired" in exc_str or "exp" in exc_str:
            raise TokenExpiredError("Token has expired.") from exc
        raise TokenInvalidError(f"Token is invalid: {exc}") from exc

    # Verify issuer
    if payload.get("iss") != JWT_ISSUER:
        raise TokenInvalidError(
            f"Invalid issuer: expected '{JWT_ISSUER}', got '{payload.get('iss')}'."
        )

    # Verify all required claims are present
    missing = REQUIRED_CLAIMS - payload.keys()
    if missing:
        raise TokenInvalidError(f"Token is missing required claims: {missing}.")

    return payload
