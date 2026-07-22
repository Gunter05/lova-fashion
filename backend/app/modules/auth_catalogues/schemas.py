"""
Pydantic request/response schemas for the Fabric Catalog module.

Enums:
    RigidityLevel  — rigid | semi-stretch | stretch
    FabricStatus   — available | unavailable | archived

Category schemas:
    CategoryCreate, CategoryUpdate, CategoryResponse

Fabric schemas:
    FabricCreate, FabricUpdate, FabricSummary, FabricDetail, FabricProperties

Selection schemas:
    SelectionResponse, SelectionConflict
"""

import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


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
