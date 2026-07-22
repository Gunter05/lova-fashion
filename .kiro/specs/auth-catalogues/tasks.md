# Implementation Plan: Fabric Catalog (Module 3)

## Overview

13 tasks covering database schema, ORM models, Pydantic schemas, CRUD layer, service
layer, API routes (client and manager), photo upload, internal properties endpoint, role
dependency, and property-based tests. All tasks build on T1 → T2 → T3 before branching
into parallel tracks for routes and tests.

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": ["T1"],
      "description": "Database migration — foundation for all other tasks"
    },
    {
      "wave": 2,
      "tasks": ["T2"],
      "description": "ORM models — depend on DB schema"
    },
    {
      "wave": 3,
      "tasks": ["T3"],
      "description": "Pydantic schemas — depend on ORM models"
    },
    {
      "wave": 4,
      "tasks": ["T4", "T5", "T11"],
      "description": "CRUD + service functions and role dependency — depend on schemas"
    },
    {
      "wave": 5,
      "tasks": ["T6", "T7", "T8", "T9", "T10"],
      "description": "API route handlers — depend on CRUD/service layer"
    },
    {
      "wave": 6,
      "tasks": ["T12"],
      "description": "Property-based tests — depend on all routes being implemented"
    },
    {
      "wave": 7,
      "tasks": ["T13"],
      "description": "Register router in main.py — final integration step"
    }
  ]
}
```

## Tasks

- [x] 1. Create database migration for `fabric_categories` and `fabrics` tables
  - Create Alembic (or raw SQL) migration that adds the two tables defined in the design.
  - Include all column types, CHECK constraints, default values, and the FK from `fabrics.category_id` → `fabric_categories.category_id`.
  - Add indexes `idx_fabrics_category_id` on `fabrics(category_id)` and `idx_fabrics_status` on `fabrics(fabric_status)`.
  - _Implements:_ data model foundation for all requirements (Req 1–7).

- [x] 2. Implement SQLAlchemy ORM models (`models.py`)
  - Implement `FabricCategory` ORM class with all columns and the `fabrics` relationship.
  - Implement `Fabric` ORM class with all columns and the `category` relationship.
  - _Implements:_ Req 1–7 (data access layer).

- [x] 3. Implement Pydantic schemas (`schemas.py`)
  - Define `RigidityLevel` and `FabricStatus` enums.
  - Define all request and response models: `CategoryCreate`, `CategoryUpdate`, `CategoryResponse`, `FabricCreate`, `FabricUpdate`, `FabricSummary`, `FabricDetail`, `FabricProperties`, `SelectionResponse`, `SelectionConflict`.
  - Apply field-level validation constraints (min/max length, ge/gt/le bounds) as specified in the design.
  - _Implements:_ Req 4 AC2–3, Req 5 AC4–6 and AC11, input validation for all endpoints.

- [x] 4. Implement category CRUD functions (`crud.py` — categories)
  - Implement `get_category`, `list_categories`, `create_category`, `update_category`, `delete_category`, and `count_fabrics_in_category`.
  - _Implements:_ Req 4 AC1, AC4, AC6 (CRUD layer).

- [x] 5. Implement fabric CRUD and business logic (`crud.py` + `service.py`)
  - Implement `get_fabric`, `list_available_fabrics` (with optional category filter and 404 guard on missing category), `create_fabric`, `update_fabric`.
  - Implement `select_fabric` (enforces status rules) and `get_alternatives` (same category, available, excluding self, sorted by `fabric_name` ASC, limit 3).
  - _Implements:_ Req 1 AC1–6, Req 2 AC1–4, Req 3 AC1–6, Req 5 AC1–12.

- [x] 6. Implement category API routes (`router.py` — categories)
  - `GET /api/v1/categories` — list all categories (any authenticated role).
  - `GET /api/v1/categories/{category_id}` — single category; return 404 if missing.
  - `POST /api/v1/categories` — create; requires `catalog_manager` role.
  - `PATCH /api/v1/categories/{category_id}` — partial update; requires `catalog_manager` role.
  - `DELETE /api/v1/categories/{category_id}` — delete; requires `catalog_manager` role; calls `count_fabrics_in_category`, returns 409 if count > 0, else deletes.
  - _Implements:_ Req 4 AC1–8.

- [x] 7. Implement client fabric routes (`router.py` — client fabrics)
  - `GET /api/v1/fabrics` — requires `client` role; calls `list_available_fabrics`; accepts optional `?category_id=` query param.
  - `GET /api/v1/fabrics/{fabric_id}` — requires `client` role; returns 404 for archived or missing; returns full detail for unavailable fabrics with `fabric_status` set.
  - `POST /api/v1/fabrics/{fabric_id}/select` — requires `client` role; calls `select_fabric`; returns 200 `SelectionResponse` or 409 `SelectionConflict`.
  - _Implements:_ Req 1 AC1–6, Req 2 AC1–4, Req 3 AC1–6.

- [x] 8. Implement manager fabric routes (`router.py` — manager fabrics)
  - `POST /api/v1/fabrics` — requires `catalog_manager` role; calls `create_fabric`; returns HTTP 201 with `FabricDetail`.
  - `PATCH /api/v1/fabrics/{fabric_id}` — requires `catalog_manager` role; partial update; returns updated `FabricDetail`.
  - `DELETE /api/v1/fabrics/{fabric_id}` — requires `catalog_manager` role; sets `fabric_status = archived` (soft-delete only, no physical row removal).
  - _Implements:_ Req 5 AC1–12.

- [x] 9. Implement photo upload endpoint and Supabase Storage helper (`storage.py`)
  - Implement `upload_fabric_photo(fabric_id, file_bytes, content_type)`: upload to bucket `fabric-photos`, return public URL, raise `StorageUploadError` on failure.
  - `POST /api/v1/fabrics/{fabric_id}/photo` — requires `catalog_manager` role; accepts `multipart/form-data`; returns 404 if fabric not found; on upload failure return 500 without updating `fabric_photo`; on success update `fabric_photo` and return `FabricDetail`.
  - _Implements:_ Req 6 AC1–5.

- [x] 10. Implement internal technical properties endpoint
  - `GET /api/v1/fabrics/{fabric_id}/properties` — any authenticated role.
  - Returns `FabricProperties` (`fabric_id`, `fabric_elasticity_rate`, `category_id`, `reference_rigidity_level`).
  - Returns 404 if fabric does not exist.
  - Returns properties even when `fabric_status = archived`.
  - _Implements:_ Req 7 AC1–4.

- [x] 11. Implement role-guard dependency (`dependencies.py`)
  - Implement `get_current_role()` and `require_role(required)` as specified in the design.
  - Return HTTP 403 for any request with a missing or unrecognised role header.
  - _Implements:_ Req 4 AC8, Req 5 AC12, Req 6 AC4.

- [x] 12. Write property-based tests
  - Set up pytest + hypothesis under `backend/app/modules/auth_catalogues/tests/`.
  - Write one test per correctness property: P1.2 (listing exclusion), P3.1 (no unavailable selection), P3.3 (alternatives count and no self-inclusion), P4.2 (category orphan prevention), P5.1 (elasticity range), P5.2 (price positivity), P7.1 (elasticity round-trip accuracy).
  - _Implements:_ correctness properties P1.2, P3.1, P3.3, P4.2, P5.1, P5.2, P7.1.

- [x] 13. Register router in `backend/main.py`
  - Import `auth_catalogues.router` and mount it with prefix `/api/v1`.
  - Verify the application starts without errors and all catalog routes appear in `/docs`.
  - _Implements:_ integration of all routes into the running application.

## Notes

- Module 1 (Authentication) owns JWT validation. This module only reads the `role` header
  via the `get_current_role()` placeholder — do not implement any login or token validation
  logic here.
- The `DELETE /fabrics/{id}` endpoint performs a **soft-delete** (sets `fabric_status =
  archived`). Physical row deletion is intentionally not implemented to preserve history.
- Photo upload (T9) requires `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` environment
  variables. Add them to `.env.example` when implementing T9.
