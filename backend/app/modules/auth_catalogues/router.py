"""
Top-level APIRouter for the auth_catalogues module.
Mounts the auth, profile, and measurement sub-routers.

Design reference: Internal Package Layout (design.md)
"""
from fastapi import APIRouter

from app.modules.auth_catalogues.auth.router import router as auth_router
from app.modules.auth_catalogues.profile.router import router as profile_router
from app.modules.auth_catalogues.measurement.router import router as measurement_router

router = APIRouter()


@router.get("/", tags=["auth_catalogues"])
def health_check():
    """Health check for the auth_catalogues module."""
    return {"status": "auth_catalogues module OK"}

# ── Auth sub-router: /auth/* ──────────────────────────────────────────────────
router.include_router(auth_router, prefix="/auth", tags=["auth"])

# ── Profile sub-router: /users/* and /admin/* (no prefix — paths are full) ───
router.include_router(profile_router, tags=["profile"])

# ── Measurement sub-router: /users/me/mensurations, /users/{cni}/mensurations ─
router.include_router(measurement_router, tags=["measurement"])
