"""
Auth_Service — registration, login, and logout. cni removed entirely.
id (UUID) is the user identifier; JWT sub/id claims use user.id.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth_user_profile.auth.repository import (
    UserRepository,
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
)
from app.modules.auth_user_profile.auth.rate_limit import rate_limiter

logger = logging.getLogger(__name__)


class RegistrationError(Exception):
    def __init__(self, field: str, message: str) -> None:
        self.field = field
        self.message = message
        super().__init__(message)


class AuthenticationError(Exception):
    pass


class AccountDeactivatedError(Exception):
    pass


class RateLimitError(Exception):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = retry_after
        super().__init__(f"Too many failed attempts. Retry after {retry_after}s.")


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = UserRepository(session)

    async def register_user(self, data: RegisterRequest) -> RegisterResponse:
        """Register a new user. id is auto-generated; role defaults to Client."""
        hashed = hash_password(data.mot_de_passe)
        try:
            user = await self._repo.create_user(
                nom=data.nom,
                email=str(data.email),
                hashed_password=hashed,
                role=UserRole.CLIENT,
            )
        except DuplicateEmailError:
            raise RegistrationError(field="email", message="Email is already registered.")

        logger.info("User registered: id=%s email=%s", user.id, user.email)
        return RegisterResponse(
            id=str(user.id),
            nom=user.nom,
            email=user.email,
            role=UserRole(user.role),
            date_inscription=user.date_inscription,
        )

    async def login_user(self, data: LoginRequest) -> LoginResponse:
        """Authenticate a user and issue a JWT. JWT subject is user.id (UUID string)."""
        email = str(data.email)

        if rate_limiter.is_locked(email):
            raise RateLimitError(retry_after=rate_limiter.retry_after(email))

        user = await self._repo.get_by_email(email)
        if user is None or not verify_password(data.mot_de_passe, user.mot_de_passe):
            rate_limiter.record_failure(email)
            raise AuthenticationError("Invalid credentials.")

        if not user.is_active:
            raise AccountDeactivatedError("Account has been deactivated.")

        rate_limiter.reset(email)
        token = issue_token(
            user_id=str(user.id),
            role=user.role.value if hasattr(user.role, "value") else str(user.role),
        )

        await self._publish_authenticated_event(
            user_id=str(user.id),
            role=str(user.role.value if hasattr(user.role, "value") else user.role),
        )

        return LoginResponse(access_token=token, token_type="bearer")

    async def logout_user(self, token: str) -> None:
        """Invalidate a JWT by adding its jti to the denylist."""
        try:
            claims = decode_token(token)
        except TokenExpiredError:
            raise
        except TokenInvalidError:
            raise

        jti: str = claims["jti"]
        exp_ts: int = claims["exp"]
        expires_at = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
        await self._repo.add_jti(jti=jti, expires_at=expires_at)

    async def _publish_authenticated_event(self, user_id: str, role: str) -> None:
        """Fire-and-forget event publish. Never blocks login."""
        try:
            from app.modules.auth_user_profile.events.bus import event_bus
            await event_bus.publish(
                "user.authenticated",
                {
                    "type": "user.authenticated",
                    "user_id": user_id,
                    "role": role,
                    "authenticated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as exc:
            logger.warning(
                "EventBus publish failed for user.authenticated (id=%s): %s", user_id, exc
            )
