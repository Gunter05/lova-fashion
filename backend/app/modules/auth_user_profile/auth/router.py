"""
Auth HTTP router — registration, login, and logout endpoints.

Design reference: API Endpoints — Authentication Endpoints (design.md)
Requirements: 1.1–1.10, 2.1–2.8, 3.1–3.4

Each handler delegates to Auth_Service and maps typed exceptions
to HTTP status codes with SCREAMING_SNAKE_CASE error envelopes.
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.auth_user_profile.auth.service import (
    AuthService,
    RegistrationError,
    AuthenticationError,
    AccountDeactivatedError,
    RateLimitError,
)
from app.modules.auth_user_profile.auth.schemas import (
    RegisterRequest,
    RegisterResponse,
    LoginRequest,
    LoginResponse,
    ErrorResponse,
)
from app.modules.auth_user_profile.auth.dependencies import get_current_user, UserClaims
from app.modules.auth_user_profile.auth.security import (
    TokenExpiredError,
    TokenInvalidError,
)

# Bearer extractor (auto_error=False: let get_current_user handle missing tokens)
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Helper: Error envelope builder ────────────────────────────────────────────

def _build_error(
    status_code: int,
    error_code: str,
    message: str,
    field: str | None = None,
    headers: dict | None = None,
) -> HTTPException:
    """
    Build an HTTPException whose detail matches the error envelope from design.md:

        {"error": "SCREAMING_SNAKE_CASE", "field": <str|null>, "message": "..."}
    """
    detail = {"error": error_code, "field": field, "message": message}
    kwargs: dict = {"status_code": status_code, "detail": detail}
    if headers:
        kwargs["headers"] = headers
    return HTTPException(**kwargs)


# ── POST /auth/register ───────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    responses={
        201: {"description": "User successfully registered"},
        409: {"description": "Duplicate email", "model": ErrorResponse},
        422: {"description": "Validation failure", "model": ErrorResponse},
    },
)
async def register(
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    """
    Register a new user account.

    **Request body:** nom, email, mot_de_passe

    **Success:** 201 Created — user profile (id, nom, email, role, date_inscription)

    **Errors:**
    - 409: Email already registered
    - 422: Invalid email format, password length, or nom length

    **Requirements:** 1.1–1.10
    """
    service = AuthService(db)

    try:
        user = await service.register_user(data)
        logger.info("User registered: id=%s email=%s", user.id, user.email)
        return user
    except RegistrationError as exc:
        logger.warning("Registration conflict: field=%s message=%s", exc.field, exc.message)
        raise _build_error(
            status.HTTP_409_CONFLICT,
            "DUPLICATE_RESOURCE",
            exc.message,
            field=exc.field,
        )


# ── POST /auth/login ──────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and receive JWT",
    responses={
        200: {"description": "Login successful", "model": LoginResponse},
        401: {"description": "Invalid credentials or deactivated account", "model": ErrorResponse},
        422: {"description": "Missing field", "model": ErrorResponse},
        429: {"description": "Rate limit exceeded", "model": ErrorResponse},
    },
)
async def login(
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """
    Authenticate a user and issue a signed JWT.

    **Request body:** email, mot_de_passe

    **Success:** 200 OK — { access_token, token_type: "bearer" }

    **Side effect:** publishes `user.authenticated` event (fire-and-forget)

    **Errors:**
    - 401: Invalid credentials (generic — no field disclosure) or deactivated account
    - 422: Missing email or password field
    - 429: 5+ consecutive failures within 15 minutes; includes `Retry-After` header

    **Requirements:** 2.1–2.8
    """
    service = AuthService(db)

    try:
        result = await service.login_user(data)
        logger.info("User authenticated: email=%s", data.email)
        return result
    except RateLimitError as exc:
        logger.warning(
            "Rate limit exceeded: email=%s retry_after=%ds",
            data.email,
            exc.retry_after,
        )
        raise _build_error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "RATE_LIMIT_EXCEEDED",
            str(exc),
            headers={"Retry-After": str(exc.retry_after)},
        )
    except AccountDeactivatedError as exc:
        logger.warning("Login on deactivated account: email=%s", data.email)
        raise _build_error(
            status.HTTP_401_UNAUTHORIZED,
            "ACCOUNT_DEACTIVATED",
            str(exc),
        )
    except AuthenticationError as exc:
        logger.warning("Authentication failure: email=%s", data.email)
        raise _build_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_CREDENTIALS",
            str(exc),
        )


# ── POST /auth/logout ─────────────────────────────────────────────────────────

@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Terminate session by invalidating JWT",
    responses={
        200: {"description": "Session terminated (idempotent)"},
        401: {"description": "Missing, expired, or invalid token", "model": ErrorResponse},
    },
)
async def logout(
    current_user: Annotated[UserClaims, Depends(get_current_user)],
    token: str | None = Depends(_oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Logout the current user by adding the JWT's `jti` to the denylist.

    **Authentication required:** Bearer JWT in Authorization header

    **Success:** 200 OK — { "message": "Session terminated." }

    Calling logout with an already-invalidated JWT returns 200 (idempotent — Req 3.2).

    **Errors:**
    - 401: Missing token (caught by `get_current_user` before this handler runs)
    - 401: Expired token — session already ended, not added to denylist (Req 3.3)
    - 401: Malformed / invalid-signature token

    **Requirements:** 3.1–3.4
    """
    service = AuthService(db)

    # `get_current_user` has already validated the token, so `token` is present.
    raw_token = token or ""

    try:
        await service.logout_user(raw_token)
        logger.info("User logged out: user_id=%s", current_user.user_id)
        return {"message": "Session terminated."}
    except TokenExpiredError:
        logger.warning("Logout with expired token: user_id=%s", current_user.user_id)
        raise _build_error(
            status.HTTP_401_UNAUTHORIZED,
            "TOKEN_EXPIRED",
            "Session has already expired.",
        )
    except TokenInvalidError:
        logger.warning("Logout with invalid token: user_id=%s", current_user.user_id)
        raise _build_error(
            status.HTTP_401_UNAUTHORIZED,
            "TOKEN_INVALID",
            "Token is invalid.",
        )
