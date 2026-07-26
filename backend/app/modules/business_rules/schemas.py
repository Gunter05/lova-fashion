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
    raw_cm: float = Field(..., description="Raw measurement from CV pipeline (cm).")
    ease_cm: float = Field(..., description="Ease delta applied to this zone (cm). Can be negative for stretch fabrics.")
    adjusted_cm: float = Field(..., description="Final adjusted cutting measurement (cm), clamped ≥ 0.")

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
    adjusted_bust_cm: float
    adjusted_waist_cm: float
    adjusted_hips_cm: float
    calculated_at: datetime

    model_config = {"from_attributes": True}


class AdjustmentListResponse(BaseModel):
    """Wrapper for the adjustments list endpoint."""
    adjustments: list[AdjustmentSummary]
    total: int


# ── Module 6 — Compatibility Engine ─────────────────────────────────
# Appended per task 3.1 / 3.2. Module 5 schemas above are untouched.

from datetime import datetime  # re-imported here for clarity (already in scope above)


# ── Module 6 Request schemas ─────────────────────────────────────────

class VerificationRequest(BaseModel):
    """
    Body for POST /verifications — triggers a full compatibility evaluation.
    Requirements: 1.1–1.2, 10.1
    """
    adjustment_id: UUID = Field(..., description="UUID of the ease-adjusted measurement record (Module 5 output).")
    model_id: UUID = Field(..., description="UUID of the garment model (Module 4).")
    fabric_id: UUID = Field(..., description="UUID of the fabric (Module 3).")
    morphology_id: UUID = Field(..., description="UUID of the client body shape classification.")
    client_id: UUID = Field(..., description="UUID of the end client requesting the evaluation.")


class CompatibilityRuleCreate(BaseModel):
    """
    Body for POST /compatibility-rules (admin only).
    Requirements: 9.1, 13.4
    """
    cut_type: str = Field(..., description="Garment cut type: 'Fitted', 'Semi-fitted', or 'Loose'.")
    fabric_property: str = Field(..., description="Fabric rigidity: 'rigid', 'semi-stretch', or 'stretch'.")
    zone_id: UUID | None = Field(None, description="Critical zone this rule targets; null for model-level rules.")
    mathematical_condition: str = Field(
        ...,
        max_length=200,
        description="Expression evaluated against 'value' (adjusted cm). E.g. 'value > 96.0'.",
    )
    severity_level: Literal["Incompatible", "Reserve"] = Field(
        ..., description="'Incompatible' = hard block; 'Reserve' = soft warning."
    )
    explanation_message: str | None = Field(
        None,
        max_length=500,
        description="Human-readable explanation shown to the client when the rule fires. Optional.",
    )
    is_active: bool = Field(True, description="Whether the rule participates in evaluations.")


class CompatibilityRuleUpdate(BaseModel):
    """
    Body for PATCH /compatibility-rules/{rule_id} (admin only).

    Immutability contract: `cut_type`, `fabric_property`, and `zone_id` are
    identity fields set at creation time and MUST NOT be present in this schema.
    If the caller attempts to change them, the service layer raises HTTP 422.
    Only the four fields below are mutable after creation.

    Requirements: 9.2, 9.3, 13.4
    """
    mathematical_condition: str | None = Field(
        None,
        max_length=200,
        description="Updated threshold expression. Leave null to keep current value.",
    )
    severity_level: Literal["Incompatible", "Reserve"] | None = Field(
        None, description="Updated severity level. Leave null to keep current value."
    )
    explanation_message: str | None = Field(
        None,
        max_length=500,
        description="Updated explanation text. Leave null to keep current value.",
    )
    is_active: bool | None = Field(
        None, description="Set false to deactivate the rule without deleting it."
    )


# ── Module 6 Response schemas ─────────────────────────────────────────

class RiskZoneResponse(BaseModel):
    """
    A single zone violation returned as part of a VerdictEvaluationResponse.
    Requirements: 6.1–6.4, 13.4
    """
    risk_id: UUID
    rule_id: UUID | None = Field(None, description="Rule that triggered this zone violation; null for morphology/fabric checks.")
    zone_id: UUID | None = Field(None, description="Critical zone involved; null for model-level violations.")
    calculated_variance: float = Field(..., description="Numeric value of the measurement at evaluation time (cm).")
    localized_verdict: Literal["Incompatible", "Reserve"]
    explanation: str = Field(..., description="Non-empty explanation text. Fallback generated if rule message is absent.")
    rule_version: int = Field(..., description="Version of the rule that was applied; preserved for audit.")

    model_config = {"from_attributes": True}


class VerdictEvaluationResponse(BaseModel):
    """
    Full compatibility evaluation result — returned by POST /verifications (201)
    and GET /verifications/{evaluation_id} (200).
    Requirements: 6.1–6.4, 10.2, 10.4, 13.4
    """
    evaluation_id: UUID
    global_status: Literal[
        "Compatible",
        "Compatible_with_Reservations",
        "Incompatible",
        "Indeterminate",
        "Failed",
    ] = Field(..., description="Aggregate verdict for the entire combination.")
    created_at: datetime
    fabric_recommendation: str | None = Field(
        None,
        description="'Highly Recommended' or 'Accepted' when the fabric is explicitly linked to the model; null otherwise.",
    )
    risk_zones: list[RiskZoneResponse] = Field(
        default_factory=list,
        description="Per-zone violations. Empty for Compatible and Indeterminate evaluations.",
    )

    model_config = {"from_attributes": True}


class CompatibilityRuleResponse(BaseModel):
    """
    Full rule record — returned by POST /compatibility-rules (201),
    PATCH /compatibility-rules/{rule_id} (200), and GET /compatibility-rules (200).
    Requirements: 9.1–9.4, 10.2, 13.4
    """
    rule_id: UUID
    cut_type: str
    fabric_property: str
    zone_id: UUID | None
    mathematical_condition: str
    severity_level: str
    explanation_message: str | None
    is_active: bool
    version: int = Field(..., description="Incremented on every PATCH; starts at 1.")
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
