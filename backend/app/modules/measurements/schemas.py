"""
Pydantic I/O schemas for Module 2 — Photo Capture & Measurement Estimation.
Task T-02.3 — Design §4
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared / nested
# ---------------------------------------------------------------------------


class MeasurementResult(BaseModel):
    """
    Embedded in SessionStatusResponse when status == 'success'.
    AC-05.2 — Design §4
    """

    bust_cm: Decimal = Field(..., description="Estimated bust circumference (cm), 1 d.p.")
    waist_cm: Decimal = Field(..., description="Estimated waist circumference (cm), 1 d.p.")
    hips_cm: Decimal = Field(..., description="Estimated hip circumference (cm), 1 d.p.")
    silhouette_code: Literal[
        "HOURGLASS", "PEAR", "INVERTED_TRIANGLE", "APPLE", "RECTANGLE"
    ] = Field(..., description="Body silhouette classification code.")

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Session creation
# ---------------------------------------------------------------------------


class SessionCreateResponse(BaseModel):
    """
    Returned by POST /sessions (HTTP 201).
    AC-01.2 — Design §5.1
    """

    session_id: UUID
    status: Literal["empty"] = "empty"
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Photo upload
# ---------------------------------------------------------------------------


class PhotoUploadResponse(BaseModel):
    """
    Returned by PUT /sessions/{session_id}/photos/{view} (HTTP 200).
    AC-02.5 — Design §5.2
    """

    session_id: UUID
    view: Literal["front", "profile"]
    photo_url: str
    status: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Stature
# ---------------------------------------------------------------------------


class StatureUpdateRequest(BaseModel):
    """
    Request body for PATCH /sessions/{session_id}/stature.
    AC-03.1 — Design §5.3
    """

    stature_cm: Decimal = Field(
        ...,
        ge=100,
        le=250,
        description="User height in centimetres (100–250).",
    )


class StatureUpdateResponse(BaseModel):
    """
    Returned by PATCH /sessions/{session_id}/stature (HTTP 200).
    AC-03.2 — Design §5.3
    """

    session_id: UUID
    entered_stature: Decimal
    status: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Process trigger
# ---------------------------------------------------------------------------


class ProcessTriggerResponse(BaseModel):
    """
    Returned by POST /sessions/{session_id}/process (HTTP 202).
    AC-04.2 — Design §5.4
    """

    session_id: UUID
    status: Literal["processing"] = "processing"
    polling_url: str


# ---------------------------------------------------------------------------
# Status polling
# ---------------------------------------------------------------------------


class SessionStatusResponse(BaseModel):
    """
    Returned by GET /sessions/{session_id}/status (HTTP 200).
    AC-05.1, AC-05.2, AC-05.3 — Design §5.5
    """

    session_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime
    retry_allowed: bool = Field(
        False,
        description="True only when status is 'failed', indicating photos may be re-uploaded.",
    )
    failure_reason: str | None = Field(
        None,
        description="Human-readable failure description, populated when status is 'failed'.",
    )
    measurements: MeasurementResult | None = Field(
        None,
        description="Raw measurements and silhouette; populated when status is 'success'.",
    )
    front_photo_url: str | None = Field(
        None,
        description="URL of the uploaded front photo, if present.",
    )
    profile_photo_url: str | None = Field(
        None,
        description="URL of the uploaded profile photo, if present.",
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Session list
# ---------------------------------------------------------------------------


class SessionListItem(BaseModel):
    """
    One item in the list returned by GET /sessions (HTTP 200).
    AC-07.1, AC-07.2 — Design §5.6
    """

    session_id: UUID
    status: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    """Wrapper for the full sessions list."""

    sessions: list[SessionListItem]
    total: int
