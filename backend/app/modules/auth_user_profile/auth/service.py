"""
Auth_Service — business logic for registration, login, and logout.

Design reference: Components and Interfaces; Authentication & Security Design
Requirements: 1.1–1.10, 2.1–2.8, 3.1–3.4, 13.6
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth_user_profile.auth.repository import (
    UserRepository,
    DuplicateCNIError,
    DuplicateEmailError,
)
from app.modules.auth_user_profile.auth.schemas import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    LoginResponse,
    UserRole,
)
from app.modules.auth_user_profile.auth.security import (
    hash_password,
    verify_password,
    issue_token,
    decode_token,
    TokenExpiredError,
    TokenInvalidError,
    JWT_EXPIRY_SECONDS,
)
from app.modules.auth_user_profile.auth.rate_limit import rate_limiter

logger = logging.getLogger(__name__)


# ── Service-layer exceptions (mapped to HTTP at the router) ───────────────────

class RegistrationError(Exception):
    """Raised with a field name and message when registration fails."""
    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(message)


class AuthenticationError(Exception):
    """Raised on invalid credentials or inactive account (generic — no field disclosure)."""


class AccountDeactivatedError(Exception):
    """Raised specifically when a deactivated account attempts to log in."""


class RateLimitError(Exception):
    """Raised when login is blocked due to too many failed attempts."""
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"Too many failed attempts. Retry after {retry_after}s.")


class LogoutError(Exception):
    """Raised on logout with an expired or missing token."""


# ── Auth_Service ──────────────────────────────────────────────────────────────

class AuthService:
    """
    Handles user registration, authentication (JWT issuance), and logout.

    Each method accepts an AsyncSession so the caller (FastAPI route handler)
    controls the transaction boundary via the `get_db` dependency.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._repo = UserRepository(session)

    async def register_user(self, data: RegisterRequest) -> RegisterResponse:
        """
        Register a new user.

        - Hashes the password with bcrypt before persisting.
        - Plaintext password is discarded immediately after hashing.
        - Raises RegistrationError on duplicate CNI or email.

        Requirements: 1.1–1.10
        """
        hashed = hash_password(data.mot_de_passe)
        # plaintext is no longer referenced after this line

        try:
            user = await self._repo.create_user(
                cni=data.cni,
                nom=data.nom,
                email=str(data.email),
                hashed_password=hashed,
                role=data.role,
            )
        except DuplicateCNIError:
            raise RegistrationError(field="cni", message="CNI is already registered.")
        except DuplicateEmailError:
            raise RegistrationError(field="email", message="Email is already registered.")

        return RegisterResponse(
            cni=user.cni,
            nom=user.nom,
            email=user.email,
            role=UserRole(user.role),
            date_inscription=user.date_inscription,
        )

    async def login_user(self, data: LoginRequest) -> LoginResponse:
        """
        Authenticate a user and issue a JWT.

        Checks:
          1. Rate-limit: raises RateLimitError if email is locked (Req 2.7).
          2. User existence and credential match.
          3. is_active flag.

        On success: resets rate-limiter, issues JWT, publishes user.authenticated event
        (fire-and-forget — EventBus failure does NOT block the login response, Req 2.8).

        Requirements: 2.1–2.8
        """
        email = str(data.email)

        # 1. Rate-limit check
        if rate_limiter.is_locked(email):
            raise RateLimitError(retry_after=rate_limiter.retry_after(email))

        # 2. Credential verification (generic 401 on any mismatch — Req 2.3, 2.4)
        user = await self._repo.get_by_email(email)
        if user is None or not verify_password(data.mot_de_passe, user.mot_de_passe):
            rate_limiter.record_failure(email)
            raise AuthenticationError("Invalid credentials.")

        # 3. Account active check (Req 13.6)
        if not user.is_active:
            raise AccountDeactivatedError("Account has been deactivated.")

        # 4. Issue JWT
        rate_limiter.reset(email)
        token = issue_token(
            cni=user.cni,
            role=user.role.value if hasattr(user.role, "value") else str(user.role),
        )

        # 5. Publish user.authenticated event (fire-and-forget, Req 2.5 & 2.8)
        await self._publish_authenticated_event(
            cni=user.cni,
            role=str(user.role.value if hasattr(user.role, "value") else user.role),
        )

        return LoginResponse(access_token=token, token_type="bearer")

    async def logout_user(self, token: str) -> None:
        """
        Invalidate a JWT by adding its jti to the denylist.

        Raises TokenExpiredError if the token is already expired (not added to denylist).
        Raises TokenInvalidError if the token is malformed.

        Requirements: 3.1–3.4
        """
        try:
            claims = decode_token(token)
        except TokenExpiredError:
            raise  # let router return 401 "session already expired"
        except TokenInvalidError:
            raise  # let router return 401 "invalid token"

        jti: str = claims["jti"]
        exp_ts: int = claims["exp"]
        expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc)

        # add_jti is idempotent — safe to call on already-denied JTIs
        await self._repo.add_jti(jti=jti, expires_at=expires_at)

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _publish_authenticated_event(self, cni: str, role: str) -> None:
        """
        Publish user.authenticated to the EventBus.
        Swallows all errors so a bus failure never blocks the login response (Req 2.8).
        """
        try:
            from app.modules.auth_user_profile.events.bus import event_bus  # lazy import
            await event_bus.publish(
                "user.authenticated",
                {
                    "type": "user.authenticated",
                    "cni": cni,
                    "role": role,
                    "authenticated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "EventBus publish failed for user.authenticated (cni=%s): %s", cni, exc
            )
