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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    """Root health endpoint."""
    return {"status": "ok", "service": "lova-fashion API"}


@app.get("/health")
def health():
    return {"status": "ok"}


# Module 1 — Auth & User Profile
app.include_router(auth_user_profile_router, prefix="/api/v1")

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
