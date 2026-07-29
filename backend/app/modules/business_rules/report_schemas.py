"""
Pydantic I/O schemas for Module 7 — Final Result & Report (Synthesis).

Covers:
- Inbound event: CompatibilityEvaluatedEvent (from Module 6 via EventBus)
- Data shapes: AdjustedMeasurementsSnapshot, DisplayHints, IncompatibleZoneItem
- API responses: ReportResponse, ReportSummary, ReportListResponse
- Outbound event: ReportSavedEvent (to Module 1 via EventBus)

Design reference: Data Models §Pydantic Schemas
Req 3 AC5 · Req 5 AC1 · Req 6 AC3 · Req 9 AC2
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ── Sub-components ────────────────────────────────────────────────────────────

class IncompatibleZoneItem(BaseModel):
    """One entry in the incompatible_zones list (Req 3 AC4)."""
    zone: str = Field(..., description="Body zone name, e.g. 'bust', 'waist', 'hips'.")
    reason: str = Field(..., description="Human-readable explanation for the incompatibility.")


class AdjustedMeasurementsSnapshot(BaseModel):
    """
    Structured snapshot of Module 5 measurement_adjustments fields.
    Stored as JSONB in rapport_mesure.adjusted_measurements (Req 2 AC1).
    """
    adjusted_bust_cm: float
    adjusted_waist_cm: float
    adjusted_hips_cm: float
    bust_ease_cm: float
    waist_ease_cm: float
    hips_ease_cm: float
    ease_source: str


class DisplayHints(BaseModel):
    """
    Derived display metadata returned in all API responses.
    NOT persisted to the database — computed on every read (Design §Components).
    """
    verdict_color: Literal["green", "orange", "red"] = Field(
        ...,
        description=(
            "'green' for compatible, 'orange' for minor_adjustments, "
            "'red' for incompatible."
        ),
    )
    highlight_zones: list[str] = Field(
        default_factory=list,
        description=(
            "Zone names to highlight in red on the frontend. "
            "Empty for compatible and minor_adjustments verdicts."
        ),
    )


# ── Inbound EventBus event (from Module 6) ────────────────────────────────────

class CompatibilityEvaluatedEvent(BaseModel):
    """
    Payload of the `compatibility.evaluated` EventBus event emitted by Module 6.
    Req 1 AC1 · Req 3 AC5
    """
    type: Literal["compatibility.evaluated"]
    emitted_at: datetime
    cni: str = Field(..., min_length=9, max_length=9,
                     description="9-character national identity number.")
    adjustment_id: uuid.UUID
    fabric_id: uuid.UUID
    model_id: uuid.UUID
    verdict: Literal["compatible", "incompatible", "minor_adjustments"]
    advice: str
    incompatible_zones: Optional[list[IncompatibleZoneItem]] = None

    @field_validator("cni")
    @classmethod
    def cni_must_be_alphanumeric(cls, v: str) -> str:
        if not v.isalnum():
            raise ValueError("CNI must be exactly 9 alphanumeric characters.")
        return v


# ── API response schemas ───────────────────────────────────────────────────────

class ReportResponse(BaseModel):
    """
    Full report detail returned by GET /reports/{report_id}.
    Req 5 AC1
    """
    report_id: uuid.UUID
    cni: str
    adjustment_id: uuid.UUID
    fabric_id: uuid.UUID
    model_id: uuid.UUID
    verdict: Literal["compatible", "incompatible", "minor_adjustments"]
    advice: str
    adjusted_measurements: AdjustedMeasurementsSnapshot
    incompatible_zones: Optional[list[IncompatibleZoneItem]] = None
    display_hints: DisplayHints
    generated_at: datetime


class ReportSummary(BaseModel):
    """
    Lightweight item returned in history and list endpoints.
    Req 6 AC3
    """
    report_id: uuid.UUID
    verdict: Literal["compatible", "incompatible", "minor_adjustments"]
    verdict_color: Literal["green", "orange", "red"]
    fabric_id: uuid.UUID
    model_id: uuid.UUID
    generated_at: datetime


class ReportListResponse(BaseModel):
    """
    Wrapper for paginated/listed report endpoints.
    Req 6 AC1–2 · Req 7 AC1–2
    """
    reports: list[ReportSummary]
    total: int


# ── Outbound EventBus event (to Module 1) ────────────────────────────────────

class ReportSavedEvent(BaseModel):
    """
    Payload of the `report.saved` EventBus event consumed by Module 1's
    `handle_report_saved` handler.

    Field names and types MUST match exactly what Module 1 expects:
    - type: str literal "report.saved"
    - cni: str (9-char CNI)
    - report_id: str (UUID serialised as plain string)
    - date_generation: str (ISO 8601 UTC timestamp string)

    Req 9 AC2 · Design §Inter-Module Data Contracts
    """
    type: Literal["report.saved"] = "report.saved"
    cni: str
    report_id: str          # UUID as plain string — Module 1 expects str
    date_generation: str    # ISO 8601 UTC string — Module 1 expects str
