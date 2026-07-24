# Design Document — Fabric Catalog (Module 3)

## Overview

The Fabric Catalog module manages the reference catalog of available fabrics and fabric
categories for the Lova Fashion custom-fit application. It is a standalone FastAPI
sub-application with no dependency on other modules. It exposes:

- A client-facing API for browsing and selecting fabrics
- A manager-facing API for full CRUD over categories and fabric references
- An internal endpoint for downstream modules to consume technical properties (elasticity
  rate and rigidity level)

**Tech stack:** Python 3.11, FastAPI, SQLAlchemy (async), PostgreSQL via Supabase,
Supabase Storage for photos, deployed on Render.com.

---

## Architecture

The module follows the existing mono-repo structure and lives entirely under
`backend/app/modules/auth_catalogues/`.

```
backend/
└── app/
    └── modules/
        └── auth_catalogues/
            ├── __init__.py
            ├── router.py          # APIRouter — all /categories and /fabrics routes
            ├── schemas.py         # Pydantic request/response models
            ├── models.py          # SQLAlchemy ORM models (FabricCategory, Fabric)
            ├── crud.py            # Pure DB query functions (no business logic)
            ├── service.py         # Business logic (status rules, alternatives, guards)
            ├── dependencies.py    # get_current_role() placeholder
            ├── storage.py         # Supabase Storage upload helper
            └── tests/
                ├── test_properties.py   # property-based tests (hypothesis)
                └── conftest.py
```

**Request flow:**
```
HTTP Request
  → FastAPI router (router.py)
    → role dependency (dependencies.py)
      → service layer (service.py)
        → CRUD layer (crud.py)
          → PostgreSQL via SQLAlchemy async session
        → Supabase Storage (storage.py) — photo uploads only
```

**External dependencies:**
- **Supabase PostgreSQL** — persistent storage
- **Supabase Storage** — fabric photo hosting via `supabase-py`
- **Render.com** — auto-deploys from `main` branch

---

## Components and Interfaces

### 3.1 API Endpoints

All routes are prefixed with `/api/v1`.

#### Categories

| Method | Path | Role required | Description |
|---|---|---|---|
| GET | `/categories` | any authenticated | List all categories |
| GET | `/categories/{category_id}` | any authenticated | Get one category |
| POST | `/categories` | `catalog_manager` | Create a category |
| PATCH | `/categories/{category_id}` | `catalog_manager` | Update a category |
| DELETE | `/categories/{category_id}` | `catalog_manager` | Delete a category |

#### Fabrics

| Method | Path | Role required | Description |
|---|---|---|---|
| GET | `/fabrics` | `client` | List available fabrics (optional `?category_id=`) |
| GET | `/fabrics/{fabric_id}` | `client` | View fabric detail |
| POST | `/fabrics/{fabric_id}/select` | `client` | Select fabric for an order |
| POST | `/fabrics` | `catalog_manager` | Create a fabric |
| PATCH | `/fabrics/{fabric_id}` | `catalog_manager` | Update a fabric |
| DELETE | `/fabrics/{fabric_id}` | `catalog_manager` | Soft-delete (archive) a fabric |
| POST | `/fabrics/{fabric_id}/photo` | `catalog_manager` | Upload / replace fabric photo |
| GET | `/fabrics/{fabric_id}/properties` | any authenticated | Internal: technical properties |

### 3.2 Pydantic Schemas (`schemas.py`)

```python
from pydantic import BaseModel, Field, UUID4
from typing import Optional
from enum import Enum

class RigidityLevel(str, Enum):
    rigid = "rigid"
    semi_stretch = "semi-stretch"
    stretch = "stretch"

class FabricStatus(str, Enum):
    available = "available"
    unavailable = "unavailable"
    archived = "archived"

# --- Categories ---
class CategoryCreate(BaseModel):
    category_name: str = Field(..., min_length=1, max_length=50)
    category_description: Optional[str] = None
    reference_rigidity_level: RigidityLevel

class CategoryUpdate(BaseModel):
    category_name: Optional[str] = Field(None, min_length=1, max_length=50)
    category_description: Optional[str] = None
    reference_rigidity_level: Optional[RigidityLevel] = None

class CategoryResponse(BaseModel):
    category_id: UUID4
    category_name: str
    category_description: Optional[str]
    reference_rigidity_level: RigidityLevel
    class Config:
        from_attributes = True

# --- Fabrics ---
class FabricCreate(BaseModel):
    fabric_name: str = Field(..., min_length=1, max_length=100)
    fabric_elasticity_rate: float = Field(..., ge=0, le=100)
    fabric_weight: float = Field(..., gt=0)
    fabric_composition: Optional[str] = None
    fabric_unit_price: float = Field(..., gt=0)
    category_id: UUID4

class FabricUpdate(BaseModel):
    fabric_name: Optional[str] = Field(None, min_length=1, max_length=100)
    fabric_elasticity_rate: Optional[float] = Field(None, ge=0, le=100)
    fabric_weight: Optional[float] = Field(None, gt=0)
    fabric_composition: Optional[str] = None
    fabric_unit_price: Optional[float] = Field(None, gt=0)
    fabric_status: Optional[FabricStatus] = None
    category_id: Optional[UUID4] = None

class FabricSummary(BaseModel):
    fabric_id: UUID4
    fabric_name: str
    fabric_unit_price: float
    fabric_photo: Optional[str]
    fabric_status: FabricStatus
    category_name: str
    class Config:
        from_attributes = True

class FabricDetail(FabricSummary):
    fabric_elasticity_rate: float
    fabric_weight: float
    fabric_composition: Optional[str]
    category_id: UUID4
    reference_rigidity_level: RigidityLevel

class FabricProperties(BaseModel):
    fabric_id: UUID4
    fabric_elasticity_rate: float
    category_id: UUID4
    reference_rigidity_level: RigidityLevel

class SelectionResponse(BaseModel):
    fabric_id: UUID4
    fabric_elasticity_rate: float
    reference_rigidity_level: RigidityLevel

class SelectionConflict(BaseModel):
    detail: str
    alternatives: list[FabricSummary]
```

### 3.3 Role Dependency (`dependencies.py`)

```python
from fastapi import Depends, HTTPException, Header
from typing import Literal

RoleType = Literal["client", "catalog_manager"]

async def get_current_role(x_user_role: str = Header(...)) -> RoleType:
    """
    Placeholder — reads the role claim from an already-validated JWT.
    Module 1 middleware populates this header before requests reach this module.
    This module does NOT validate the JWT itself.
    """
    if x_user_role not in ("client", "catalog_manager"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return x_user_role

def require_role(required: RoleType):
    async def check(role: RoleType = Depends(get_current_role)):
        if role != required:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return role
    return check
```

### 3.4 Business Logic (`service.py`)

Key service functions:

**`list_available_fabrics(db, category_id=None)`**
- Queries fabrics where `fabric_status = available`
- If `category_id` is provided, validates the category exists first (raises 404 if not)
- Returns joined results including `category_name`

**`select_fabric(db, fabric_id)`**
- Returns 404 if fabric does not exist or is `archived`
- Returns 409 + `get_alternatives()` if fabric is `unavailable`
- Returns `SelectionResponse` on success

**`get_alternatives(db, fabric)`**
- Same category, `fabric_status = available`, excludes self
- Ordered by `fabric_name` ASC, limited to 3

**`delete_category(db, category_id)`**
- Counts associated fabrics; returns 409 if count > 0
- Permanently deletes if count = 0

**`upload_fabric_photo(fabric_id, file_bytes, content_type)` in `storage.py`**
- Uploads to Supabase Storage bucket `fabric-photos`
- Returns public URL on success
- Raises `StorageUploadError` on failure (caller maps to HTTP 500)
- `fabric_photo` field is only updated after a successful upload

---

## Data Models

### Database Tables

#### `fabric_categories`

| Column | Type | Constraints |
|---|---|---|
| `category_id` | UUID | PK, default gen_random_uuid() |
| `category_name` | VARCHAR(50) | NOT NULL |
| `category_description` | TEXT | NULLABLE |
| `reference_rigidity_level` | VARCHAR(12) | NOT NULL, CHECK IN ('rigid','semi-stretch','stretch') |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now() |

#### `fabrics`

| Column | Type | Constraints |
|---|---|---|
| `fabric_id` | UUID | PK, default gen_random_uuid() |
| `fabric_name` | VARCHAR(100) | NOT NULL |
| `fabric_elasticity_rate` | NUMERIC(5,2) | NOT NULL, CHECK 0 <= x <= 100 |
| `fabric_weight` | NUMERIC(8,2) | NOT NULL, CHECK x > 0 |
| `fabric_composition` | TEXT | NULLABLE |
| `fabric_unit_price` | NUMERIC(10,2) | NOT NULL, CHECK x > 0 |
| `fabric_photo` | TEXT | NULLABLE |
| `fabric_status` | VARCHAR(11) | NOT NULL, default 'available', CHECK IN ('available','unavailable','archived') |
| `category_id` | UUID | NOT NULL, FK → fabric_categories(category_id) |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default now() |

**Indexes:**
- `idx_fabrics_category_id` on `fabrics(category_id)` — supports category filter
- `idx_fabrics_status` on `fabrics(fabric_status)` — supports status filter on listings

### SQLAlchemy ORM Models (`models.py`)

```python
import uuid
from sqlalchemy import Column, String, Numeric, Text, ForeignKey, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base

class FabricCategory(Base):
    __tablename__ = "fabric_categories"
    category_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_name = Column(String(50), nullable=False)
    category_description = Column(Text, nullable=True)
    reference_rigidity_level = Column(String(12), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(),
                        onupdate=func.now(), nullable=False)
    fabrics = relationship("Fabric", back_populates="category")

class Fabric(Base):
    __tablename__ = "fabrics"
    fabric_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fabric_name = Column(String(100), nullable=False)
    fabric_elasticity_rate = Column(Numeric(5, 2), nullable=False)
    fabric_weight = Column(Numeric(8, 2), nullable=False)
    fabric_composition = Column(Text, nullable=True)
    fabric_unit_price = Column(Numeric(10, 2), nullable=False)
    fabric_photo = Column(Text, nullable=True)
    fabric_status = Column(String(11), nullable=False, default="available")
    category_id = Column(UUID(as_uuid=True),
                         ForeignKey("fabric_categories.category_id"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(),
                        onupdate=func.now(), nullable=False)
    category = relationship("FabricCategory", back_populates="fabrics")
```

---

## Correctness Properties

These properties are the basis for the property-based test suite (pytest + hypothesis):

### Property 1: Listing exclusion

For any database state containing fabrics with `fabric_status` of `unavailable` or `archived`, a `GET /fabrics` request SHALL return a list that contains none of those fabrics. Corresponds to P1.2.

**Validates: Requirements 1.3**

### Property 2: No unavailable selection

For any fabric with `fabric_status != available`, a `POST /fabrics/{id}/select` request SHALL never return HTTP 200. Corresponds to P3.1.

**Validates: Requirements 3.2**

### Property 3: Alternatives count and no self-inclusion

For any unavailable fabric selection attempt, the `alternatives` array in the 409 response SHALL contain at most 3 items and SHALL NOT include the `fabric_id` of the rejected fabric. Corresponds to P3.3.

**Validates: Requirements 3.2**

### Property 4: Category orphan prevention

For any category that has at least one associated fabric, a `DELETE /categories/{id}` request SHALL return HTTP 409 and leave the category and its fabrics unchanged. Corresponds to P4.2.

**Validates: Requirements 4.7**

### Property 5: Elasticity range invariant

For any `POST /fabrics` or `PATCH /fabrics/{id}` request where `fabric_elasticity_rate` is outside the closed interval [0, 100], the system SHALL return HTTP 422 and make no change to the database. Corresponds to P5.1.

**Validates: Requirements 5.4**

### Property 6: Price positivity invariant

For any `POST /fabrics` or `PATCH /fabrics/{id}` request where `fabric_unit_price` ≤ 0, the system SHALL return HTTP 422 and make no change to the database. Corresponds to P5.2.

**Validates: Requirements 5.5**

### Property 7: Elasticity round-trip accuracy

For any fabric created with a known `fabric_elasticity_rate` value R, a subsequent `GET /fabrics/{id}/properties` request SHALL return `fabric_elasticity_rate` equal to R (no precision loss or transformation). Corresponds to P7.1.

**Validates: Requirements 7.1**

---

## Error Handling

| Scenario | HTTP Status | Notes |
|---|---|---|
| Resource not found (fabric / category) | 404 | Standard `{"detail": "..."}` |
| Archived fabric requested by client | 404 | Treated as non-existent |
| Unavailable fabric selection | 409 | Includes `alternatives[]` in body |
| Category deletion with fabrics | 409 | Standard `{"detail": "..."}` |
| Validation failure | 422 | FastAPI default `detail` array |
| Insufficient role | 403 | Standard `{"detail": "..."}` |
| Supabase Storage upload failure | 500 | `fabric_photo` left unchanged |

---

## Testing Strategy

- **Framework:** pytest + hypothesis (compatible with the existing Python/FastAPI stack)
- **Location:** `backend/app/modules/auth_catalogues/tests/`
- **Approach:** one test function per correctness property (P1.2, P3.1, P3.3, P4.2, P5.1,
  P5.2, P7.1); hypothesis generates boundary-covering inputs automatically
- **Integration points:** the `/properties` endpoint is tested with a round-trip assertion
  to verify elasticity accuracy (P7.1)
