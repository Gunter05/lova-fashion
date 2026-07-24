# Design Document — Module 4: Pattern Catalog and Constraints

## 1. Architecture Overview

Module 4 lives inside `backend/app/modules/auth_catalogues/` alongside Modules 1 and 3.
It exposes a FastAPI router mounted at `/api/v1/models`.

```
Client / Admin
      │  JWT (role claim validated by Module 1)
      ▼
FastAPI Router  (/api/v1/models/...)
      │
      ├── Service layer (state machine, completeness gate, snapshot logic)
      │       │
      │       ├── CRUD layer (async SQLAlchemy, Supabase PostgreSQL)
      │       │
      │       ├── Storage helper (Supabase Storage — inspiration images)
      │       │
      │       └── AI Analyzer client (synchronous HTTP call, 10 s timeout)
      │
Module 3 fabric validation
(GET /api/v1/fabrics/{fabric_id}/properties — internal call)
```

### Key design decisions

- **Synchronous AI analysis** — the image upload endpoint (`POST /models/init`) blocks until
  the AI Analyzer responds, then either creates the Draft and returns 201, or rejects with
  422/503 and leaves no MODEL row.
- **Single router, status-aware dispatch** — `PATCH /models/{model_id}` inspects the current
  `status` and branches: Draft → edit-in-place; Published → snapshot-then-edit; Archived →
  409.
- **JSONB snapshot** — `model_snapshot.zones` and `model_snapshot.fabrics` are stored as
  JSONB arrays so historical data is truly decoupled from live join tables.
- **Module 3 coupling at assignment time only** — fabric availability is validated when an
  admin calls `PUT /models/{id}/fabrics`. The live `model_fabric` rows keep the `fabric_id`
  reference; if a fabric is later archived in Module 3, existing assignments are preserved
  (the assignment was valid when made) but a warning is surfaced when the admin views the
  model profile.

---

## 2. Data Model

### 2.1 Table: `model`

```sql
CREATE TABLE model (
    model_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name    VARCHAR(100) NOT NULL,
    description   TEXT,
    photo_url     VARCHAR(255) NOT NULL,
    garment_type  VARCHAR(50)  NOT NULL
                  CHECK (garment_type IN (
                      'Dress','Shirt','Blouse','Trousers','Skirt',
                      'Jacket','Coat','Shorts','Suit','Traditional')),
    cut_type      VARCHAR(20)  NOT NULL
                  CHECK (cut_type IN ('Fitted','Semi-fitted','Loose')),
    status        VARCHAR(20)  NOT NULL DEFAULT 'Draft'
                  CHECK (status IN ('Draft','Published','Archived')),
    version       INT          NOT NULL DEFAULT 1,
    creator_id    UUID         NOT NULL REFERENCES auth.users(id),
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);
```

### 2.2 Table: `critical_zone` (reference / seed table)

```sql
CREATE TABLE critical_zone (
    zone_id     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_name   VARCHAR(50) NOT NULL UNIQUE,
    description TEXT
);

-- Seed values
INSERT INTO critical_zone (zone_name, description) VALUES
    ('Chest',     'Circumference around the fullest part of the chest'),
    ('Waist',     'Circumference at the natural waistline'),
    ('Hips',      'Circumference around the fullest part of the hips'),
    ('Shoulders', 'Width across the shoulders'),
    ('Neck',      'Circumference at the base of the neck'),
    ('Thighs',    'Circumference around the fullest part of the thigh'),
    ('Ankles',    'Circumference around the ankle');
```

### 2.3 Table: `model_critical_zone` (join)

```sql
CREATE TABLE model_critical_zone (
    model_id UUID NOT NULL REFERENCES model(model_id) ON DELETE CASCADE,
    zone_id  UUID NOT NULL REFERENCES critical_zone(zone_id),
    PRIMARY KEY (model_id, zone_id)
);
```

### 2.4 Table: `model_fabric` (join — references Module 3)

```sql
CREATE TABLE model_fabric (
    model_id  UUID NOT NULL REFERENCES model(model_id) ON DELETE CASCADE,
    fabric_id UUID NOT NULL,   -- logical reference to Module 3 fabric table
    PRIMARY KEY (model_id, fabric_id)
);
```

`fabric_id` has no DB-level foreign key to Module 3 to keep modules loosely coupled.
Referential integrity is enforced at the service layer during assignment.

### 2.5 Table: `model_snapshot` (immutability / audit)

```sql
CREATE TABLE model_snapshot (
    snapshot_id      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id         UUID        NOT NULL,   -- logical ref, no FK (allow decouple)
    snapshot_version INT         NOT NULL,
    model_name       VARCHAR(100) NOT NULL,
    description      TEXT,
    garment_type     VARCHAR(50)  NOT NULL,
    cut_type         VARCHAR(20)  NOT NULL,
    photo_url        VARCHAR(255) NOT NULL,
    status           VARCHAR(20)  NOT NULL,
    creator_id       UUID         NOT NULL,
    zones            JSONB        NOT NULL,  -- [{zone_id, zone_name}, ...]
    fabrics          JSONB        NOT NULL,  -- [{fabric_id, fabric_name}, ...]
    snapshotted_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    UNIQUE (model_id, snapshot_version)
);
```

Zones and fabrics are embedded as JSONB so the snapshot is self-contained — even if a zone
or fabric row is later deleted, the historical snapshot remains intact.

---

## 3. State Machine

```
                    POST /models/init
                    (client, AI success)
           ──────────────────────────────►  [ Draft ]
                                                │
                          POST .../publish      │   POST .../archive
                          (admin, gate OK)      │   (admin)
                                 │              ▼
                          [ Published ] ──────► [ Archived ]  (terminal)
                               │  ▲
    PATCH (admin) + snapshot   │  │  POST .../publish
    written on PATCH           │  │  (admin, version++)
                               └──┘
```

**Valid transitions:**

| From       | Action                     | To         | Side-effect                    |
|------------|----------------------------|------------|--------------------------------|
| —          | `POST /models/init`        | Draft      | MODEL row created, version=1   |
| Draft      | `POST .../publish` (gate✓) | Published  | status → Published             |
| Draft      | `POST .../archive`         | Archived   | status → Archived              |
| Published  | `PATCH` (admin)            | Published  | Snapshot written, fields updated |
| Published  | `POST .../publish` (gate✓) | Published  | version incremented by 1       |
| Published  | `POST .../archive`         | Archived   | status → Archived              |
| Archived   | any                        | —          | 409 — terminal state           |

---

## 4. Snapshotting Strategy

When an administrator PATCHes a **Published** model, the service executes the following
sequence inside a **single database transaction**:

```
BEGIN

1. SELECT model + zones + fabrics  (current live state)

2. INSERT INTO model_snapshot (
       model_id, snapshot_version,
       model_name, description, garment_type, cut_type,
       photo_url, status, creator_id,
       zones  = JSON array of {zone_id, zone_name},
       fabrics = JSON array of {fabric_id, fabric_name}
   )

3. UPDATE model
   SET    <only fields present in request body>,
          updated_at = now()
   WHERE  model_id = :id

COMMIT   ← success: both snapshot + update persisted atomically
ROLLBACK ← on any exception: neither change persisted → HTTP 500
```

**Version increment** is separate and happens only when the admin calls
`POST /models/{id}/publish` on a Published model (after edits). This keeps the PATCH
response free from version ambiguity and lets admins make multiple field corrections before
incrementing the public version.

**Snapshot is NOT created at republish** — it is created at edit time (PATCH). The publish
action merely increments `version` and re-validates the completeness gate.

---

## 5. AI Analyzer Integration

The AI Analyzer is treated as an external synchronous HTTP service. For the initial release
a stub implementation is used; it can be replaced with a real CV model endpoint later.

```
Input  (multipart image bytes)
Output {
    garment_type:    str,          # one of the 10-value enum
    cut_type:        str,          # Fitted | Semi-fitted | Loose
    critical_zones:  [str],        # list of zone_name values
    confidence:      float         # 0.0 – 1.0
}
```

**Decision logic:**

| Condition                            | System action                        |
|--------------------------------------|--------------------------------------|
| confidence ≥ 0.70                    | Proceed to create Draft              |
| confidence < 0.70                    | Return 422 — ask for clearer image   |
| AI unreachable / timeout (10 s)      | Return 503 — do not create Draft     |
| AI returns unexpected response shape | Return 503 — do not create Draft     |

Zone names returned by the AI are matched against the `critical_zone` seed table by
`zone_name` (case-insensitive). Unrecognised zone names from the AI are silently dropped
(the admin can assign zones manually). If no zones match, the Draft is still created but
with an empty zone list — the completeness gate will block publication until zones are added.

**Order of operations in `POST /models/init`:**

```
1. Validate file format and size (422 if invalid)
2. Upload image to Supabase Storage  (500 if fails)
3. Call AI Analyzer with image bytes  (503 if unreachable; 422 if low confidence)
4. Map AI output to garment_type + cut_type + zone_ids
5. INSERT model row + model_critical_zone rows  (all in one transaction)
6. Return 201 with Draft profile
```

If step 3 or 4 fails after a successful upload in step 2, the orphaned image in Supabase
Storage is deleted in a best-effort cleanup before returning the error response.

---

## 6. API Endpoints

### 6.1 `POST /api/v1/models/init`

**Role:** `client`

**Request:** `multipart/form-data` with a single file field `image`.

**Success response `201`:**
```json
{
  "model_id": "uuid",
  "model_name": "Dress #1",
  "garment_type": "Dress",
  "cut_type": "Fitted",
  "status": "Draft",
  "version": 1,
  "photo_url": "https://...",
  "zones": [{"zone_id": "uuid", "zone_name": "Chest"}],
  "fabrics": []
}
```

**Error codes:** 401, 403, 422 (format/size/low-confidence), 500 (storage), 503 (AI down)

---

### 6.2 `GET /api/v1/models`

**Role:** any authenticated

**Query params:** `garment_type` (optional, enum)

**Success response `200`:**
```json
{
  "total": 12,
  "items": [
    {
      "model_id": "uuid",
      "model_name": "Sheath Dress",
      "garment_type": "Dress",
      "cut_type": "Fitted",
      "version": 2,
      "photo_url": "https://..."
    }
  ]
}
```

**Error codes:** 401, 422 (invalid garment_type filter)

---

### 6.3 `GET /api/v1/models/{model_id}`

**Role:** any authenticated (client-facing — Draft/Archived → 404)

**Success response `200`:**
```json
{
  "model_id": "uuid",
  "model_name": "Sheath Dress",
  "description": "...",
  "garment_type": "Dress",
  "cut_type": "Fitted",
  "status": "Published",
  "version": 2,
  "photo_url": "https://...",
  "zones": [{"zone_id": "uuid", "zone_name": "Chest"}],
  "fabrics": [{"fabric_id": "uuid", "fabric_name": "Wax Vlisco"}]
}
```

**Error codes:** 401, 404, 422 (invalid UUID)

---

### 6.4 `PATCH /api/v1/models/{model_id}`

**Role:** `administrator`

**Behaviour:** Branches on `status`:
- `Draft` → edit fields in-place, no snapshot.
- `Published` → write snapshot then apply edits (transactional).
- `Archived` → 409.

**Request body** (all fields optional):
```json
{
  "model_name": "Updated Name",
  "description": "New description",
  "garment_type": "Blouse",
  "cut_type": "Loose"
}
```

**Success response `200`:** Full model object (same shape as 6.3).

**Error codes:** 401, 403, 404, 409 (wrong status), 422 (validation), 500 (snapshot failure)

---

### 6.5 `PUT /api/v1/models/{model_id}/zones`

**Role:** `administrator`

**Request body:**
```json
{ "zone_ids": ["uuid1", "uuid2"] }
```

**Success response `200`:**
```json
{ "zones": [{"zone_id": "uuid", "zone_name": "Chest"}] }
```

**Error codes:** 401, 403, 404, 422 (unknown zone_id)

---

### 6.6 `PUT /api/v1/models/{model_id}/fabrics`

**Role:** `administrator`

**Request body:**
```json
{ "fabric_ids": ["uuid1", "uuid2"] }
```

**Validation:** Each `fabric_id` checked against Module 3 internal endpoint
(`GET /api/v1/fabrics/{id}/properties`) before any DB write. All-or-nothing.

**Success response `200`:**
```json
{ "fabrics": [{"fabric_id": "uuid", "fabric_name": "Wax Vlisco"}] }
```

**Error codes:** 401, 403, 404, 422 (unknown or unavailable fabric_id)

---

### 6.7 `POST /api/v1/models/{model_id}/publish`

**Role:** `administrator`

**Behaviour:**
- `Draft` → run completeness gate → set `status = Published` → return 200.
- `Published` → run completeness gate → `version += 1` → return 200.
- `Archived` → 409.

**Success response `200`:** Full model object.

**Error codes:** 401, 403, 404, 409 (already published / archived), 422 (gate failure)

---

### 6.8 `POST /api/v1/models/{model_id}/archive`

**Role:** `administrator`

**Success response `200`:**
```json
{ "model_id": "uuid", "status": "Archived" }
```

**Error codes:** 401, 403, 404, 409 (already archived), 500 (DB failure mid-update)

---

### 6.9 `GET /api/v1/models/{model_id}/constraints`

**Role:** any authenticated (internal endpoint — Published + Archived both served)

**Success response `200`:**
```json
{
  "model_id": "uuid",
  "model_name": "Sheath Dress",
  "version": 2,
  "garment_type": "Dress",
  "cut_type": "Fitted",
  "zones": [{"zone_id": "uuid", "zone_name": "Chest"}],
  "fabrics": [{"fabric_id": "uuid", "fabric_name": "Wax Vlisco"}]
}
```

**Error codes:** 401, 404 (Draft or non-existent), 422 (invalid UUID)

---

## 7. Module 3 Integration

Fabric validation at `PUT /models/{id}/fabrics` calls Module 3's internal properties
endpoint for each `fabric_id`:

```
GET /api/v1/fabrics/{fabric_id}/properties
→ 200: { fabric_id, fabric_elasticity_rate, category_id, reference_rigidity_level, fabric_status }
→ 404: fabric does not exist
```

Validation rules applied before any DB write:
1. If `fabric_id` returns 404 → HTTP 422 with `{"error": "fabric_not_found", "fabric_id": "..."}`
2. If `fabric_status != "available"` → HTTP 422 with `{"error": "fabric_not_available", "fabric_id": "..."}`
3. Duplicates in the input list are deduplicated before validation.
4. Only if all IDs pass validation does the service atomically delete existing `model_fabric`
   rows and insert the new set.

Since Module 3 and Module 4 are in the same FastAPI process (same `auth_catalogues` module
group), this "call" is a direct Python function call to the Module 3 CRUD layer rather than
an HTTP round-trip, avoiding network overhead.

---

## 8. Error Handling Summary

| Scenario | HTTP | State side-effect |
|---|---|---|
| Invalid image format | 422 | None |
| Image exceeds 10 MB | 422 | None |
| AI confidence < 0.70 | 422 | None (orphan image cleaned up) |
| AI unreachable / timeout | 503 | None (orphan image cleaned up) |
| Supabase Storage upload fails | 500 | None |
| Unauthenticated request | 401 | None |
| Insufficient role | 403 | None |
| Model not found | 404 | None |
| Invalid UUID path param | 422 | None |
| PATCH on Archived model | 409 | None |
| Publish with 0 zones | 422 | Status stays unchanged |
| Publish with 0 fabrics | 422 | Status stays unchanged |
| Publish already-published (no edits) | 409 | None |
| Publish from Archived | 409 | None |
| Snapshot write failure | 500 | Full rollback — live MODEL unchanged |
| Unknown fabric_id at assignment | 422 | MODEL_FABRIC unchanged |
| Unavailable fabric at assignment | 422 | MODEL_FABRIC unchanged |
| Archive already-archived model | 409 | None |
| DB error during archive | 500 | Status reverted to pre-archive value |

---

## 9. File Structure

```
backend/app/modules/auth_catalogues/
├── models.py          # SQLAlchemy ORM: Model, CriticalZone,
│                      #   ModelCriticalZone, ModelFabric, ModelSnapshot
├── schemas.py         # Pydantic v2 request/response schemas
│                      #   (ModelCreate, ModelUpdate, ModelOut,
│                      #    ZoneAssignment, FabricAssignment,
│                      #    ConstraintsOut, CatalogListOut)
├── service.py         # Business logic:
│                      #   init_model(), edit_model(), assign_zones(),
│                      #   assign_fabrics(), publish_model(),
│                      #   archive_model(), _write_snapshot(),
│                      #   _completeness_gate()
├── storage.py         # Supabase Storage helpers:
│                      #   upload_inspiration_image(), delete_image()
├── ai_client.py       # AI Analyzer HTTP client (stub + real impl):
│                      #   analyze_image() → AIAnalysisResult
├── crud.py            # Async DB queries (no business logic):
│                      #   get_model(), list_models(), create_model(),
│                      #   update_model(), get_zones_for_model(),
│                      #   set_zones(), get_fabrics_for_model(),
│                      #   set_fabrics(), create_snapshot()
├── router.py          # FastAPI route definitions (9 endpoints)
├── dependencies.py    # Role guards: require_admin(), require_client(),
│                      #   require_authenticated()
└── migrations/
    └── 002_create_model_tables.sql   # model, critical_zone,
                                      # model_critical_zone, model_fabric,
                                      # model_snapshot + seed zones
```

---

## 10. Property-Based Testing Strategy

Each correctness property maps to one or more test strategies in
`backend/app/modules/auth_catalogues/tests/test_properties.py`.

| Property | Strategy |
|---|---|
| **P1.2** — No draft on AI failure | Inject mock AI returning `confidence=0.50`; assert no MODEL row exists after POST /models/init |
| **P1.3** — Client-only invariant | Generate random non-client roles (admin); assert POST /models/init returns 403 |
| **P2.2** — Exclusion invariant | Generate N Draft and Archived models; assert none appear in GET /models listing |
| **P4.2** — Enum invariant | Generate arbitrary string for `garment_type`/`cut_type`; assert PATCH returns 422 |
| **P6.1** — Completeness gate | Generate Draft with 0 zones or 0 fabrics; assert publish returns 422 |
| **P7.1** — Snapshot-before-update | PATCH Published model N times; assert MODEL_SNAPSHOT count increases by N |
| **P7.2** — Version monotonicity | Publish/PATCH/publish cycle repeated K times; assert `version` strictly increases each cycle |
| **P7.4** — Atomicity under failure | Inject DB fault after snapshot INSERT but before MODEL UPDATE; assert MODEL unchanged and no partial snapshot row |
| **P8.1** — Client invisibility | Archive model; assert GET /models excludes it and GET /models/{id} returns 404 |
| **P9.2** — Archived accessibility | Archive model; assert GET /models/{id}/constraints returns 200 with full data |
