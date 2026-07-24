# Implementation Plan: Module 4 — Pattern Catalog and Constraints

## Overview

19 tasks covering database migration, ORM models, Pydantic schemas, role-guard dependencies,
Supabase Storage helper, AI Analyzer client, CRUD layer, service functions (init, edit,
zones, fabrics, publish, archive), FastAPI router (9 endpoints), property-based tests,
smoke/integration tests, and router registration. The critical path runs sequentially from
the DB migration through to the router; service functions and tests can be parallelised
within their respective waves.

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
      "description": "SQLAlchemy ORM models — depend on DB schema"
    },
    {
      "wave": 3,
      "tasks": ["T3"],
      "description": "Pydantic v2 schemas — depend on ORM models"
    },
    {
      "wave": 4,
      "tasks": ["T4", "T5", "T6", "T7"],
      "description": "Role guards, Storage helper, AI client, CRUD — all depend on schemas; can run in parallel"
    },
    {
      "wave": 5,
      "tasks": ["T8", "T9", "T10", "T11", "T12", "T13", "T14", "T15"],
      "description": "Service functions — all depend on CRUD (T7); can run in parallel"
    },
    {
      "wave": 6,
      "tasks": ["T16"],
      "description": "FastAPI router — depends on all service functions"
    },
    {
      "wave": 7,
      "tasks": ["T17", "T18", "T19"],
      "description": "Tests and router registration — depend on router (T16); can run in parallel"
    }
  ]
}
```

## Tasks

Tasks are ordered chronologically: database migration → ORM models → Pydantic schemas →
CRUD layer → service layer → router → tests. Each task references the requirement(s) and
acceptance criteria it implements.

---

- [x] 1. Write and apply database migration `002_create_model_tables.sql`
  - Create `critical_zone` table with seed rows (Chest, Waist, Hips, Shoulders, Neck, Thighs, Ankles)
  - Create `model` table with all columns, CHECK constraints for `garment_type`, `cut_type`, `status`
  - Create `model_critical_zone` join table with composite PK and CASCADE delete
  - Create `model_fabric` join table with composite PK and CASCADE delete
  - Create `model_snapshot` table with JSONB `zones` and `fabrics` columns and UNIQUE(model_id, snapshot_version)
  - **Implements:** design §2 (full schema)

- [x] 2. Define SQLAlchemy ORM models in `models.py`
  - `Model` mapped to `model` table (all columns, enums as Python `Enum` types)
  - `CriticalZone` mapped to `critical_zone`
  - `ModelCriticalZone` association mapped to `model_critical_zone`
  - `ModelFabric` association mapped to `model_fabric`
  - `ModelSnapshot` mapped to `model_snapshot` (JSONB columns as `JSON` type)
  - **Implements:** design §2, design §9

- [x] 3. Define Pydantic v2 schemas in `schemas.py`
  - `GarmentTypeEnum` and `CutTypeEnum` Python enums matching DB CHECK values
  - `ModelInitResponse` (Draft creation response — Req 1 AC1)
  - `ModelListItem` and `ModelListOut` with `total` field (Req 2 AC1–2)
  - `ModelDetailOut` with `zones` and `fabrics` lists, no `creator_id` (Req 3 AC1)
  - `ModelUpdateRequest` (all fields Optional; Req 4 AC2)
  - `ZoneAssignmentRequest` with `zone_ids: list[UUID]` (Req 4 AC9)
  - `FabricAssignmentRequest` with `fabric_ids: list[UUID]` (Req 5 AC1)
  - `ConstraintsOut` (Req 9 AC1)
  - `ArchiveOut` (Req 8 AC1)
  - **Implements:** design §9 (schemas.py)

- [x] 4. Implement role-guard dependencies in `dependencies.py`
  - `require_client(token)` — raises 403 if role != `client` (Req 1 AC4)
  - `require_admin(token)` — raises 403 if role != `administrator` (Req 4 AC8, Req 5 AC5, Req 6 AC6, Req 7 AC7, Req 8 AC7)
  - `require_authenticated(token)` — raises 401 if no valid JWT (Req 2 AC7, Req 3 AC6, Req 9 AC7)
  - **Implements:** design §9 (dependencies.py)

- [x] 5. Implement Supabase Storage helper in `storage.py`
  - `upload_inspiration_image(file_bytes, filename) -> str` — returns public URL; raises `StorageUploadError` on failure (Req 1 AC7)
  - `delete_image(photo_url)` — best-effort cleanup called when AI analysis fails after a successful upload (design §5)
  - **Implements:** Req 1 AC1, AC7; design §5

- [x] 6. Implement AI Analyzer client in `ai_client.py`
  - `AIAnalysisResult` dataclass: `garment_type`, `cut_type`, `critical_zones: list[str]`, `confidence: float`
  - `analyze_image(image_bytes: bytes) -> AIAnalysisResult` — synchronous HTTP call, 10 s timeout
  - Raises `AILowConfidenceError` when `confidence < 0.70` (Req 1 AC2)
  - Raises `AIUnavailableError` when unreachable or unexpected response (Req 1 AC3)
  - Stub implementation returns deterministic fixture data for local dev/tests
  - **Implements:** Req 1 AC2–3; design §5

- [x] 7. Implement async CRUD functions in `crud.py`
  - `create_model(db, model_data) -> Model`
  - `get_model(db, model_id) -> Model | None`
  - `list_models(db, garment_type=None) -> tuple[list[Model], int]` — returns items + total count (Req 2 AC1)
  - `update_model(db, model_id, fields: dict) -> Model`
  - `set_zones(db, model_id, zone_ids: list[UUID])` — delete-all then insert (Req 4 AC9–11)
  - `get_zones_for_model(db, model_id) -> list[CriticalZone]`
  - `set_fabrics(db, model_id, fabric_ids: list[UUID])` — delete-all then insert (Req 5 AC1)
  - `get_fabrics_for_model(db, model_id) -> list[dict]` — returns list of {fabric_id, fabric_name}
  - `create_snapshot(db, model: Model) -> ModelSnapshot` — reads live zones+fabrics, builds JSONB, inserts (Req 7 AC1, AC8)
  - `count_zones(db, model_id) -> int`
  - `count_fabrics(db, model_id) -> int`
  - **Implements:** design §9 (crud.py)

- [x] 8. Implement Module 3 fabric validation helper in `service.py`
  - `validate_fabrics_from_module3(fabric_ids: list[UUID]) -> None` — calls Module 3 CRUD directly (same process); raises `FabricNotFoundError` or `FabricNotAvailableError` (Req 5 AC2–3); deduplicates input before validation (Req 5 AC8)
  - **Implements:** Req 5 AC1–3, AC8; design §7

- [x] 9. Implement completeness gate in `service.py`
  - `completeness_gate(db, model_id) -> None` — raises `MissingZonesError`, `MissingFabricsError`, or `MissingZonesAndFabricsError` when counts are zero (Req 6 AC2–4)
  - **Implements:** Req 6 AC2–4, AC8; Req 7 AC4; design §4

- [x] 10. Implement `init_model()` service function
  - Validate file format and size (Req 1 AC5–6)
  - Upload to Supabase Storage (Req 1 AC7)
  - Call `analyze_image()` — on failure clean up uploaded image and re-raise (Req 1 AC2–3)
  - Map AI zone names to `zone_id` values via DB lookup (design §5)
  - Compute sequential `model_name` as `[garment_type] #[N]` (Req 1 AC8)
  - Insert MODEL row + CRITICAL_ZONE rows in a single transaction (Req 1 AC1)
  - Return Draft profile
  - **Implements:** Req 1 AC1–8; P1.1, P1.2, P1.3, P1.4

- [x] 11. Implement `edit_model()` service function (status-aware dispatch)
  - Load model; raise 404 if not found (Req 4 AC6, Req 7)
  - If `status = Archived` → raise 409 (Req 4 AC7)
  - If `status = Draft` → validate fields, update in-place, return (Req 4 AC1–5)
  - If `status = Published` → open transaction, call `create_snapshot()`, apply updates, commit (Req 7 AC1–2, AC8)
  - Rollback and raise 500 on snapshot failure (Req 7 AC2; P7.4)
  - **Implements:** Req 4 AC1–8; Req 7 AC1–2, AC5–6, AC8; P4.1–4, P7.1, P7.4

- [x] 12. Implement `assign_zones()` service function
  - Validate each `zone_id` exists in `critical_zone` table — raise 422 on unknown (Req 4 AC10)
  - Accept empty list (clears all zones) (Req 4 AC11)
  - Call `crud.set_zones()` — atomically replaces entries (Req 4 AC9)
  - **Implements:** Req 4 AC9–11; P4.4

- [x] 13. Implement `assign_fabrics()` service function
  - Deduplicate input (Req 5 AC8)
  - Call `validate_fabrics_from_module3()` for each unique ID (Req 5 AC1–3)
  - Accept empty list (clears all fabrics) (Req 5 AC4)
  - Call `crud.set_fabrics()` atomically (Req 5 AC1)
  - If model is Published, do NOT increment version (Req 5 AC7)
  - **Implements:** Req 5 AC1–8; P5.1, P5.2, P5.3

- [x] 14. Implement `publish_model()` service function
  - Load model; raise 404 if not found (Req 6 AC5)
  - If `status = Archived` → raise 409 (Req 6 AC8)
  - If `status = Published` → run completeness gate → `version += 1` → return (Req 7 AC3–4)
  - If `status = Draft` → run completeness gate → set `status = Published` → return (Req 6 AC1–4)
  - **Implements:** Req 6 AC1–8; Req 7 AC3–4; P6.1, P6.2, P6.3, P7.2

- [x] 15. Implement `archive_model()` service function
  - Load model; raise 404 if not found (Req 8 AC5)
  - If `status = Archived` → raise 409 (Req 8 AC6; P8.3)
  - Set `status = Archived` in a transaction; on DB error rollback and raise 500 (Req 8 AC8)
  - **Implements:** Req 8 AC1, AC5–8; P8.3

- [x] 16. Implement FastAPI router in `router.py` with all 9 endpoints
  - `POST /models/init` → `init_model()`, role: client (Req 1)
  - `GET /models` → `list_models()`, role: authenticated (Req 2)
  - `GET /models/{model_id}` → client-facing detail, 404 for Draft/Archived (Req 3)
  - `PATCH /models/{model_id}` → `edit_model()`, role: admin (Req 4, Req 7)
  - `PUT /models/{model_id}/zones` → `assign_zones()`, role: admin (Req 4)
  - `PUT /models/{model_id}/fabrics` → `assign_fabrics()`, role: admin (Req 5)
  - `POST /models/{model_id}/publish` → `publish_model()`, role: admin (Req 6, Req 7)
  - `POST /models/{model_id}/archive` → `archive_model()`, role: admin (Req 8)
  - `GET /models/{model_id}/constraints` → internal endpoint, Published+Archived served (Req 9)
  - Mount router in `main.py` at `/api/v1/models`
  - **Implements:** design §6

- [x] 17. Write property-based tests in `tests/test_properties.py`
  - **P1.2** — Mock AI returning `confidence=0.50`; POST /models/init; assert 422 and no MODEL row
  - **P1.3** — POST /models/init with admin JWT; assert 403
  - **P2.2** — Create N Draft + Archived models; GET /models; assert none appear in response
  - **P4.2** — PATCH with arbitrary invalid `garment_type`/`cut_type` strings; assert 422
  - **P6.1** — Publish Draft with 0 zones; assert 422. Publish Draft with 0 fabrics; assert 422
  - **P7.1** — PATCH Published model K times; assert MODEL_SNAPSHOT count = K
  - **P7.2** — Publish/PATCH/publish cycle; assert `version` strictly increases each cycle
  - **P7.4** — Inject DB fault mid-snapshot transaction; assert MODEL unchanged and no partial snapshot
  - **P8.1** — Archive model; GET /models assert excluded; GET /models/{id} assert 404
  - **P9.2** — Archive model; GET /models/{id}/constraints assert 200 with full data
  - **Implements:** all correctness properties from requirements §P1–P9

- [-] 18. Write smoke / integration tests in `tests/test_smoke.py`
  - Happy path: upload image → Draft created → admin edits → assigns zones + fabrics → publish → client views detail → internal constraints endpoint returns data
  - Edit-and-republish cycle: PATCH Published → snapshot exists → publish → version incremented
  - Archive flow: archive Published model → client gets 404 → constraints endpoint returns 200
  - **Implements:** end-to-end validation of full workflow

- [x] 19. Register router in `main.py` and verify `/health` still passes
  - Uncomment / add `auth_catalogues_router` mount at `/api/v1/models`
  - Run `pytest backend/ -x` and confirm all Module 4 tests pass
  - **Implements:** deployment integration (design §9)

---

## Notes

### Implementation context
- Module 4 lives in `backend/app/modules/auth_catalogues/` alongside Modules 1 and 3.
- The FastAPI router is mounted at `/api/v1/models` in `backend/main.py`.
- Authentication (JWT parsing, role extraction) is delegated to Module 1; this module only
  consumes the already-validated `role` claim via the dependency guards.

### Module 3 coupling
- Fabric availability is validated at assignment time only (`PUT /models/{id}/fabrics`).
  The service calls Module 3's CRUD layer directly (same Python process) — no HTTP round-trip.
- There is no DB-level foreign key from `model_fabric.fabric_id` to the Module 3 fabric
  table; referential integrity is enforced at the service layer.
- If a fabric is archived in Module 3 after assignment, existing `model_fabric` rows are
  preserved. The admin is shown a warning when viewing the model profile.

### Snapshotting
- A `model_snapshot` row is created inside the same transaction as the PATCH on a Published
  model. If the snapshot INSERT fails the entire transaction is rolled back (HTTP 500).
- `version` is incremented only on `POST /models/{id}/publish` for an already-Published
  model — NOT on the PATCH itself. This separates edit cycles from version bumps.
- Snapshot zones and fabrics are stored as JSONB so they remain intact even if the
  underlying `critical_zone` or Module 3 fabric rows are later deleted.

### AI Analyzer
- The AI Analyzer stub (`ai_client.py`) returns deterministic fixture data for local
  development and testing. Swap in the real CV endpoint by updating `analyze_image()`.
- Confidence threshold is 0.70. Below this threshold the endpoint returns HTTP 422 and no
  MODEL row is created. A failed Storage upload is cleaned up best-effort before returning.

### Testing status
- Tasks 1–16 and 19: fully implemented and passing.
- Task 17 (property-based tests): implemented and passing.
- Task 18 (smoke / integration tests): in progress — core happy path scenarios drafted,
  edge-case flows pending completion.

### State machine summary
| From      | Action              | To        | Side-effect                       |
|-----------|---------------------|-----------|-----------------------------------|
| —         | POST /models/init   | Draft     | MODEL row created, version=1      |
| Draft     | POST .../publish    | Published | Completeness gate checked         |
| Draft     | POST .../archive    | Archived  | status → Archived                 |
| Published | PATCH               | Published | Snapshot written, fields updated  |
| Published | POST .../publish    | Published | version incremented by 1          |
| Published | POST .../archive    | Archived  | status → Archived                 |
| Archived  | any write action    | —         | HTTP 409 — terminal state         |
