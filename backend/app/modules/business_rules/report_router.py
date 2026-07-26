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

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Header, status
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


# ── Auth helpers (reads from x-user-cni / x-user-role headers set by Module 1) ──────

def _get_caller(
    x_user_cni: Annotated[str | None, Header()] = None,
    x_user_role: Annotated[str | None, Header()] = None,
) -> tuple[str, str]:
    """
    Extract caller identity from the headers populated by Module 1's JWT middleware.

    Raises HTTP 401 if either header is absent or CNI is not 9 characters.
    NFR-02
    """
    if not x_user_cni or not x_user_role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials are required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if len(x_user_cni) != 9:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user identity in request headers.",
        )
    return x_user_cni, x_user_role


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

    Auth: Client role only (enforced via x-user-role header).
    Req 6 AC1–4
    """
    caller_cni, caller_role = caller

    if caller_role.lower() != "client":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only clients may access their own report list.",
        )

    reports = await _service.list_reports_for_client(caller_cni, db)
    summaries = ReportService.to_summary_list(reports)
    return ReportListResponse(reports=summaries, total=len(summaries))


# ── GET /reports/client/{cni} ────────────────────────────────────────────────

@router.get(
    "/client/{cni}",
    response_model=ReportListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all reports for a specific client (Tailor / Admin only)",
)
async def list_client_reports(
    cni: str,
    caller: tuple[str, str] = Depends(_get_caller),
    db: AsyncSession = Depends(get_db),
) -> ReportListResponse:
    """
    Return all reports for the client identified by `cni`, newest first.
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

    # _assert_user_exists is called inside list_reports_for_client_as_tailor → 404
    reports = await _service.list_reports_for_client_as_tailor(cni, db)
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
    caller_cni, caller_role = caller

    report = await _service.get_report(report_id, caller_cni, caller_role, db)

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
        cni=report.cni,
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
