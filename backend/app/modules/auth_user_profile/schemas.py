"""
Pydantic request/response schemas for the Fabric Catalog (Module 3) and
Pattern Catalog (Module 4).

Module 3 enums:
    RigidityLevel  — rigid | semi-stretch | stretch
    FabricStatus   — available | unavailable | archived

Module 3 schemas:
    CategoryCreate, CategoryUpdate, CategoryResponse
    FabricCreate, FabricUpdate, FabricSummary, FabricDetail, FabricProperties
    SelectionResponse, SelectionConflict

Module 4 enums:
    GarmentTypeEnum  — Dress | Shirt | Blouse | Trousers | Skirt |
                       Jacket | Coat | Shorts | Suit | Traditional
    CutTypeEnum      — Fitted | Semi-fitted | Loose
    StatusEnum       — Draft | Published | Archived

Module 4 nested item schemas:
    ZoneItem, FabricItem

Module 4 request schemas:
    ModelUpdateRequest, ZoneAssignmentRequest, FabricAssignmentRequest

Module 4 response schemas:
    ModelInitResponse, ModelListItem, ModelListOut,
    ModelDetailOut, ArchiveOut, ConstraintsOut
"""

import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RigidityLevel(str, Enum):
    rigid = "rigid"
    semi_stretch = "semi-stretch"
    stretch = "stretch"


class FabricStatus(str, Enum):
    available = "available"
    unavailable = "unavailable"
    archived = "archived"


# ---------------------------------------------------------------------------
# Category schemas
# ---------------------------------------------------------------------------

class CategoryCreate(BaseModel):
    """Payload for creating a new fabric category."""

    category_name: str = Field(..., min_length=1, max_length=50)
    category_description: Optional[str] = None
    reference_rigidity_level: RigidityLevel


class CategoryUpdate(BaseModel):
    """Partial-update payload for an existing fabric category.

    All fields are optional; only provided fields are applied.
    """

    category_name: Optional[str] = Field(None, min_length=1, max_length=50)
    category_description: Optional[str] = None
    reference_rigidity_level: Optional[RigidityLevel] = None


class CategoryResponse(BaseModel):
    """Response schema for a fabric category."""

    model_config = ConfigDict(from_attributes=True)

    category_id: uuid.UUID
    category_name: str
    category_description: Optional[str]
    reference_rigidity_level: RigidityLevel


# ---------------------------------------------------------------------------
# Fabric schemas
# ---------------------------------------------------------------------------

class FabricCreate(BaseModel):
    """Payload for creating a new fabric reference."""

    fabric_name: str = Field(..., min_length=1, max_length=100)
    # Elasticity rate is a percentage: 0 % – 100 %
    fabric_elasticity_rate: float = Field(..., ge=0, le=100)
    # Weight must be strictly positive
    fabric_weight: float = Field(..., gt=0)
    fabric_composition: Optional[str] = None
    # Unit price must be strictly positive
    fabric_unit_price: float = Field(..., gt=0)
    category_id: uuid.UUID


class FabricUpdate(BaseModel):
    """Partial-update payload for an existing fabric reference.

    All fields are optional; only provided fields are applied.
    """

    fabric_name: Optional[str] = Field(None, min_length=1, max_length=100)
    fabric_elasticity_rate: Optional[float] = Field(None, ge=0, le=100)
    fabric_weight: Optional[float] = Field(None, gt=0)
    fabric_composition: Optional[str] = None
    fabric_unit_price: Optional[float] = Field(None, gt=0)
    fabric_photo: Optional[str] = None
    fabric_status: Optional[FabricStatus] = None
    category_id: Optional[uuid.UUID] = None


class FabricSummary(BaseModel):
    """Compact fabric representation used in list responses."""

    model_config = ConfigDict(from_attributes=True)

    fabric_id: uuid.UUID
    fabric_name: str
    fabric_unit_price: float
    fabric_photo: Optional[str]
    fabric_status: FabricStatus
    # Denormalised from the parent FabricCategory for convenience
    category_name: str


class FabricDetail(FabricSummary):
    """Full fabric representation including technical and category fields.

    Inherits all fields from FabricSummary and adds the technical properties
    needed for the detail view and downstream modules.
    """

    fabric_elasticity_rate: float
    fabric_weight: float
    fabric_composition: Optional[str]
    category_id: uuid.UUID
    reference_rigidity_level: RigidityLevel


# ---------------------------------------------------------------------------
# Internal / selection schemas
# ---------------------------------------------------------------------------

class FabricProperties(BaseModel):
    """Technical properties returned by the internal /properties endpoint.

    Consumed by the Ease Margin Calculation Engine and the Compatibility
    Verification Engine.
    """

    fabric_id: uuid.UUID
    fabric_elasticity_rate: float
    category_id: uuid.UUID
    reference_rigidity_level: RigidityLevel


class SelectionResponse(BaseModel):
    """Successful fabric-selection confirmation (HTTP 200)."""

    fabric_id: uuid.UUID
    fabric_elasticity_rate: float
    reference_rigidity_level: RigidityLevel


class SelectionConflict(BaseModel):
    """Conflict response when the selected fabric is unavailable (HTTP 409).

    Includes up to 3 alternative fabrics from the same category.
    """

    detail: str
    alternatives: list[FabricSummary]


# ===========================================================================
# Module 4 — Pattern Catalog
# ===========================================================================

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class GarmentTypeEnum(str, Enum):
    """Garment type enum matching the DB CHECK constraint (§2.1)."""
    Dress = "Dress"
    Shirt = "Shirt"
    Blouse = "Blouse"
    Trousers = "Trousers"
    Skirt = "Skirt"
    Jacket = "Jacket"
    Coat = "Coat"
    Shorts = "Shorts"
    Suit = "Suit"
    Traditional = "Traditional"


class CutTypeEnum(str, Enum):
    """Cut type enum matching the DB CHECK constraint (§2.1)."""
    Fitted = "Fitted"
    Semi_fitted = "Semi-fitted"
    Loose = "Loose"


class StatusEnum(str, Enum):
    """Model lifecycle status enum."""
    Draft = "Draft"
    Published = "Published"
    Archived = "Archived"


# ---------------------------------------------------------------------------
# Nested item schemas (reused across multiple responses)
# ---------------------------------------------------------------------------

class ZoneItem(BaseModel):
    """A single critical zone reference embedded in model responses."""

    model_config = ConfigDict(from_attributes=True)

    zone_id: uuid.UUID
    zone_name: str


class FabricItem(BaseModel):
    """A single fabric reference embedded in model responses."""

    model_config = ConfigDict(from_attributes=True)

    fabric_id: uuid.UUID
    fabric_name: str


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class ModelInitResponse(BaseModel):
    """
    HTTP 201 response returned after a successful Draft creation.

    Implements: Req 1 AC1 — Draft profile with AI-populated fields.
    """

    model_config = ConfigDict(from_attributes=True)

    model_id: uuid.UUID
    model_name: str
    garment_type: GarmentTypeEnum
    cut_type: CutTypeEnum
    status: StatusEnum
    version: int
    photo_url: str
    zones: list[ZoneItem]
    fabrics: list[FabricItem]


class ModelListItem(BaseModel):
    """
    Compact model representation used in catalog list responses.

    Implements: Req 2 AC1-2 — fields required in each list item.
    """

    model_config = ConfigDict(from_attributes=True)

    model_id: uuid.UUID
    model_name: str
    garment_type: GarmentTypeEnum
    cut_type: CutTypeEnum
    version: int
    photo_url: str


class ModelListOut(BaseModel):
    """
    Paginated catalog list response.

    Implements: Req 2 AC1 — includes `total` count of Published models.
    """

    total: int
    items: list[ModelListItem]


class ModelDetailOut(BaseModel):
    """
    Full model profile returned for GET /models/{model_id}.

    Implements: Req 3 AC1 — all fields including zones and fabrics lists;
    creator_id is intentionally excluded.
    """

    model_config = ConfigDict(from_attributes=True)

    model_id: uuid.UUID
    model_name: str
    description: Optional[str]
    garment_type: GarmentTypeEnum
    cut_type: CutTypeEnum
    status: StatusEnum
    version: int
    photo_url: str
    zones: list[ZoneItem]
    fabrics: list[FabricItem]


class ArchiveOut(BaseModel):
    """
    Response body returned after a successful archive operation.

    Implements: Req 8 AC1.
    """

    model_config = ConfigDict(from_attributes=True)

    model_id: uuid.UUID
    status: StatusEnum


class ConstraintsOut(BaseModel):
    """
    Model constraints response consumed by downstream modules (Module 6 / 7).

    Implements: Req 9 AC1 — includes zones and fabrics; served for both
    Published and Archived models.
    """

    model_config = ConfigDict(from_attributes=True)

    model_id: uuid.UUID
    model_name: str
    version: int
    garment_type: GarmentTypeEnum
    cut_type: CutTypeEnum
    zones: list[ZoneItem]
    fabrics: list[FabricItem]


# ---------------------------------------------------------------------------
# Request / input schemas
# ---------------------------------------------------------------------------

class ModelUpdateRequest(BaseModel):
    """
    Partial-update payload for PATCH /models/{model_id}.

    All fields are Optional; only fields present in the request body are
    applied.  Applies to both Draft (Req 4 AC2) and Published (Req 7 AC5)
    models.

    Implements: Req 4 AC2.
    """

    model_name: Optional[str] = Field(
        None,
        description="1–100 non-whitespace characters after trimming.",
    )
    description: Optional[str] = Field(
        None,
        max_length=1000,
        description="Optional free-text description, maximum 1 000 characters.",
    )
    garment_type: Optional[GarmentTypeEnum] = None
    cut_type: Optional[CutTypeEnum] = None

    @field_validator("model_name", mode="before")
    @classmethod
    def validate_model_name(cls, v: Optional[str]) -> Optional[str]:
        """
        Trim whitespace and enforce 1–100 character constraint.

        Returns None unchanged (field is optional). A non-None value that is
        whitespace-only or exceeds 100 characters after trimming raises a
        ValueError, which Pydantic converts to HTTP 422.
        """
        if v is None:
            return v
        trimmed = v.strip()
        if len(trimmed) == 0:
            raise ValueError("model_name must not be empty or whitespace-only.")
        if len(trimmed) > 100:
            raise ValueError(
                f"model_name must not exceed 100 characters after trimming "
                f"(got {len(trimmed)})."
            )
        return trimmed


class ZoneAssignmentRequest(BaseModel):
    """
    Request body for PUT /models/{model_id}/zones.

    An empty list is valid and clears all zone assignments (Req 4 AC11).

    Implements: Req 4 AC9.
    """

    zone_ids: list[uuid.UUID]


class FabricAssignmentRequest(BaseModel):
    """
    Request body for PUT /models/{model_id}/fabrics.

    An empty list is valid and removes all fabric assignments (Req 5 AC4).

    Implements: Req 5 AC1.
    """

    fabric_ids: list[uuid.UUID]
