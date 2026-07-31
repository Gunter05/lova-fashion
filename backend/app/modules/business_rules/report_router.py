"""
HTTP router for Module 7 — Final Result & Report (Synthesis).

Exposes three read-only endpoints:
  GET /api/v1/reports/me              — authenticated Client: own report history
  GET /api/v1/reports/client/{cni}    — Tailor / Admin: reports for a specific client
  GET /api/v1/reports/{report_id}     — any authorised caller: one full report

IMPORTANT: /reports/me is registered BEFORE /reports/{report_id} to prevent
FastAPI from interpreting the literal string "me" as a UUID path parameter.

No POST / PUT / PATCH / DELETE routes — report creation is event-driven only.

Design reference: Components and Interfaces §HTTP Router
Req 5 · Req 6 · Req 7
"""
from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.business_rules.report_schemas import (
    ReportListResponse,
    ReportResponse,
    AdjustedMeasurementsSnapshot,
)
from app.modules.business_rules.report_service import ReportService, build_display_hints

router = APIRouter(prefix="/reports", tags=["reports"])
_service = ReportService()

_bearer_scheme = HTTPBearer(auto_error=True)

_JWT_SECRET: str = os.environ.get("JWT_SECRET", "dev-secret-change-me-32-chars-min!")
_JWT_ALGORITHM: str = "HS256"
_JWT_ISSUER: str = os.environ.get("JWT_ISSUER", "lova-fashion-auth")


# ── Auth dependency — decodes Bearer JWT → (cni, role) ───────────────────────

async def _get_caller(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> tuple[str, str]:
    """
    Decode the Bearer JWT issued by Module 1 and return (user_id, role).

    Raises HTTP 401 if the token is missing, expired, or has an invalid signature.
    NFR-02
    """
    try:
        payload = jwt.decode(
            credentials.credentials,
            _JWT_SECRET,
            algorithms=[_JWT_ALGORITHM],
            options={"verify_aud": False},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token d'authentification invalide ou expiré.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str | None = payload.get("user_id") or payload.get("sub")
    role: str | None = payload.get("role")

    if not user_id or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token incomplet : claims 'user_id' ou 'role' manquants.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user_id, role


# ── GET /reports/me ──────────────────────────────────────────────────────────
# Registered FIRST to prevent "me" being parsed as a UUID.

@router.get(
    "/me",
    response_model=ReportListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all reports for the authenticated client",
)
async def list_my_reports(
    caller: tuple[str, str] = Depends(_get_caller),
    db: AsyncSession = Depends(get_db),
) -> ReportListResponse:
    """
    Return all reports for the authenticated client, ordered newest first.
    Returns `reports=[]` and `total=0` when no reports exist.

    Auth:
      - Client: returns their own reports.
      - Admin / administrator: returns all existing reports.
      - Tailor / catalog_manager: returns an empty list.
    """
    caller_id, caller_role = caller

    role_lower = caller_role.lower()
    if role_lower in ("admin", "administrator"):
        reports = await _service.list_all_reports(db)
    elif role_lower in ("tailor", "catalog_manager"):
        reports = []
    elif role_lower == "client":
        reports = await _service.list_reports_for_client(caller_id, db)
    else:
        reports = []

    summaries = ReportService.to_summary_list(reports)
    return ReportListResponse(reports=summaries, total=len(summaries))


# ── GET /reports/client/{cni} ────────────────────────────────────────────────

@router.get(
    "/client/{user_id}",
    response_model=ReportListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all reports for a specific client (Tailor / Admin only)",
)
async def list_client_reports(
    user_id: str,
    caller: tuple[str, str] = Depends(_get_caller),
    db: AsyncSession = Depends(get_db),
) -> ReportListResponse:
    """
    Return all reports for the client identified by `user_id` (UUID), newest first.
    Returns `reports=[]` and `total=0` when no reports exist.

    Auth: Tailor or Admin role only.
    Req 7 AC1–5
    """
    _, caller_role = caller

    if caller_role.lower() not in ("tailor", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only tailors and admins may access client report lists.",
        )

    reports = await _service.list_reports_for_client_as_tailor(user_id, db)
    summaries = ReportService.to_summary_list(reports)
    return ReportListResponse(reports=summaries, total=len(summaries))


# ── GET /reports/{report_id} ─────────────────────────────────────────────────
# Registered LAST to avoid shadowing /reports/me and /reports/client/{cni}.

@router.get(
    "/{report_id}",
    response_model=ReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a specific report by ID",
)
async def get_report(
    report_id: uuid.UUID,
    caller: tuple[str, str] = Depends(_get_caller),
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    """
    Return the full detail of a report, including adjusted measurements,
    verdict, advice, incompatible zones, and display hints.

    - Client: may only retrieve their own reports (403 otherwise).
    - Tailor / Admin: may retrieve any report.

    Req 5 AC1–5
    """
    caller_id, caller_role = caller

    report = await _service.get_report(report_id, caller_id, caller_role, db)

    # Deserialise the JSONB snapshot back into the typed model
    snapshot = AdjustedMeasurementsSnapshot.model_validate(report.adjusted_measurements)

    # Deserialise incompatible_zones from JSONB (may be None or list of dicts)
    from app.modules.business_rules.report_schemas import IncompatibleZoneItem
    zones = None
    if report.incompatible_zones:
        zones = [IncompatibleZoneItem.model_validate(z) for z in report.incompatible_zones]

    hints = build_display_hints(report.verdict, zones)

    return ReportResponse(
        report_id=report.id_report,
        user_id=str(report.user_id) if hasattr(report, 'user_id') else str(getattr(report, 'cni', '')),
        adjustment_id=report.adjustment_id,
        fabric_id=report.fabric_id,
        model_id=report.model_id,
        verdict=report.verdict,          # type: ignore[arg-type]
        advice=report.advice,
        adjusted_measurements=snapshot,
        incompatible_zones=zones,
        display_hints=hints,
        generated_at=report.generated_at,
    )
