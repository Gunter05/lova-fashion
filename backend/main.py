from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.modules.auth_user_profile.router import router as auth_user_profile_router
from app.modules.auth_catalogues.router import router as auth_catalogues_router
from app.modules.measurements.router import router as measurements_router
from app.modules.business_rules.router import router as business_rules_router


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
    from app.db.session import AsyncSessionLocal

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

    yield
    # Nothing to tear down for in-process bus; add broker.close() here when migrating.


app = FastAPI(
    title="Remote Custom-Fit Styling — AWS re:Deploy 2026",
    lifespan=lifespan,
)


@app.get("/")
def root():
    """Root health endpoint."""
    return {"status": "ok", "service": "lova-fashion API"}


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth_user_profile_router, prefix="/api/v1")
app.include_router(auth_catalogues_router, prefix="/api/v1")
app.include_router(measurements_router, prefix="/api/v1/measurements", tags=["measurements"])
app.include_router(business_rules_router, prefix="/api/v1/ease", tags=["ease-allowance"])
