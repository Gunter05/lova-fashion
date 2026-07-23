"""
Pydantic I/O schemas for Module 5 — Ease Allowance Calculation Engine.
Task T-02.3 — Design §4
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ── Request ──────────────────────────────────────────────────────────

class AdjustmentRequest(BaseModel):
    """
    Body for POST /adjustments — requests ease calculation.
    """
    session_id: UUID = Field(..., description="UUID of the capture session (must be in 'success' status).")
    fabric_id: UUID = Field(..., description="UUID of the fabric from the catalog.")


# ── Nested detail ────────────────────────────────────────────────────

class ZoneDetail(BaseModel):
    """
    Raw + ease + adjusted value for one measurement zone.
    Provides full transparency per zone (AC-03.1).
    """
    raw_cm: Decimal = Field(..., description="Raw measurement from CV pipeline (cm).")
    ease_cm: Decimal = Field(..., description="Ease delta applied to this zone (cm). Can be negative for stretch fabrics.")
    adjusted_cm: Decimal = Field(..., description="Final adjusted cutting measurement (cm), clamped ≥ 0.")

    model_config = {"from_attributes": True}


# ── Response — Full adjustment detail ────────────────────────────────

class AdjustmentResponse(BaseModel):
    """
    Full adjustment record — returned by POST (201/200) and GET by ID.
    AC-01.5, AC-05.1, AC-07.1 — Design §4
    """
    adjustment_id: UUID
    session_id: UUID
    fabric_id: UUID
    fabric_name: str
    elasticity_category: str | None = Field(
        None,
        description="Elasticity category from fabric catalog. None when ease_source is 'default_fallback'.",
    )
    ease_source: Literal["rule", "default_fallback"] = Field(
        ...,
        description="'rule' = delta from ease_rules; 'default_fallback' = unknown category, +3 cm applied.",
    )
    bust: ZoneDetail
    waist: ZoneDetail
    hips: ZoneDetail
    calculated_at: datetime
    data_integrity_warning: bool = Field(
        False,
        description="True if the source session is no longer in 'success' status (AC-07.1).",
    )

    model_config = {"from_attributes": True}


# ── Response — List item summary ─────────────────────────────────────

class AdjustmentSummary(BaseModel):
    """
    Lightweight item for GET /sessions/{session_id}/adjustments list.
    AC-06.1 — Design §4
    """
    adjustment_id: UUID
    fabric_id: UUID
    fabric_name: str
    elasticity_category: str | None
    ease_source: str
    adjusted_bust_cm: Decimal
    adjusted_waist_cm: Decimal
    adjusted_hips_cm: Decimal
    calculated_at: datetime

    model_config = {"from_attributes": True}


class AdjustmentListResponse(BaseModel):
    """Wrapper for the adjustments list endpoint."""
    adjustments: list[AdjustmentSummary]
    total: int
