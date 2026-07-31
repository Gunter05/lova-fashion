from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.modules.auth_user_profile.router import router as auth_user_profile_router
from app.modules.measurements.router import router as measurements_router
from app.modules.business_rules.router import router as ease_router, compatibility_router
from app.modules.auth_catalogues.router import router as auth_catalogues_router
from app.modules.business_rules.report_router import router as report_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Register event handlers at application startup.

    Handlers are wrapped in session-factory closures so each event delivery
    gets its own AsyncSession (isolation + automatic commit/rollback).
    """
    from app.modules.auth_user_profile.events.bus import event_bus
    from app.modules.auth_user_profile.events.handlers import (
        make_measurements_handler,
        make_report_saved_handler,
        make_profile_data_request_handler,
    )
    from app.modules.business_rules.report_handler import (
        make_compatibility_evaluated_handler,
    )
    from app.db.session import AsyncSessionLocal

    # Module 1 — Auth & User Profile event handlers
    event_bus.subscribe(
        "measurements.estimated",
        make_measurements_handler(AsyncSessionLocal),
    )
    event_bus.subscribe(
        "report.saved",
        make_report_saved_handler(AsyncSessionLocal),
    )
    event_bus.subscribe(
        "profile_data_request",
        make_profile_data_request_handler(AsyncSessionLocal, event_bus),
    )

    # Module 7 — Final Result & Report event handler
    event_bus.subscribe(
        "compatibility.evaluated",
        make_compatibility_evaluated_handler(AsyncSessionLocal),
    )

    yield
    # Nothing to tear down for in-process bus; add broker.close() here when migrating.


app = FastAPI(
    title="Remote Custom-Fit Styling — AWS re:Deploy 2026",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Global Robust Exception Handlers
# ---------------------------------------------------------------------------
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging

_api_logger = logging.getLogger("lova_fashion_api")

from fastapi.encoders import jsonable_encoder

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    _api_logger.error(f"Erreur de validation de la requête : {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Erreur de validation des données fournies.", "errors": jsonable_encoder(exc.errors())},
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    _api_logger.warning(f"HTTP Exception: {exc.status_code} - {exc.detail}")
    headers = getattr(exc, "headers", None)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers,
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    _api_logger.exception("Une erreur non gérée est survenue lors du traitement de la requête :")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Une erreur serveur interne est survenue. Veuillez réessayer plus tard."},
    )

# ---------------------------------------------------------------------------
# CORS — allow requests from local dev and Vercel deployments
# ---------------------------------------------------------------------------
import os

_EXTRA_ORIGINS = [
    o.strip()
    for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",        # Vite dev server
        "http://localhost:3000",        # fallback local port
        "https://lova-fashion.vercel.app",  # production Vercel domain
        *_EXTRA_ORIGINS,               # extra origins via env var
    ],
    # Covers all Vercel preview URLs for this project (change on every deploy)
    allow_origin_regex=r"https://lova-fashion(-[a-z0-9]+)*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# JWT Header Injection Middleware — maps Bearer JWT to upstream auth headers
# ---------------------------------------------------------------------------
from starlette.middleware.base import BaseHTTPMiddleware

class HeaderInjectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. ALWAYS strip incoming x-user-role, x-user-id, and x-user-cni to prevent header spoofing
        headers_list = list(request.scope.get("headers", []))
        headers_list = [
            (k, v) for k, v in headers_list
            if k.lower() not in (b"x-user-role", b"x-user-id", b"x-user-cni")
        ]
        request.scope["headers"] = headers_list

        # 2. Extract and decode Bearer token if present
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
            try:
                from app.modules.auth_user_profile.auth.security import decode_token
                payload = decode_token(token)
                user_id = payload.get("user_id") or payload.get("sub")
                role = payload.get("role")
                if user_id and role:
                    mapped_role = "client"
                    if role == "Tailor":
                        mapped_role = "catalog_manager"
                    elif role == "Admin":
                        mapped_role = "administrator"

                    headers_list.append((b"x-user-role", mapped_role.encode("utf-8")))
                    headers_list.append((b"x-user-id", str(user_id).encode("utf-8")))
                    headers_list.append((b"x-user-cni", str(user_id).encode("utf-8")))

                    request.scope["headers"] = headers_list
            except Exception:
                pass
        return await call_next(request)

app.add_middleware(HeaderInjectionMiddleware)


@app.get("/")
def root():
    """Root health endpoint."""
    return {"status": "ok", "service": "lova-fashion API"}


@app.get("/health")
def health():
    return {"status": "ok"}


# Module 1 — Auth & User Profile
app.include_router(auth_user_profile_router, prefix="/api/v1")
app.include_router(auth_user_profile_router, prefix="/auth-catalogues")

# Module 2 — Measurement Sessions
app.include_router(measurements_router, prefix="/api/v1/measurements", tags=["measurements"])

# Module 3 (Fabric Catalog) + Module 4 (Pattern Catalog)
app.include_router(auth_catalogues_router, prefix="/api/v1", tags=["catalogues"])

# Module 5 — Ease Allowance Calculation Engine
app.include_router(ease_router, prefix="/api/v1/ease", tags=["ease-allowance"])

# Module 6 — Compatibility Engine
app.include_router(compatibility_router, prefix="/api/v1/compatibility", tags=["compatibility"])

# Module 7 — Final Result & Report
app.include_router(report_router, prefix="/api/v1")
