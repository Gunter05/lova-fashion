# Design — Module 5: Ease Allowance Calculation Engine
# (Moteur de calcul d'aisance — Architecture technique)

## 1. Module Position in the System

```
┌──────────────────────────────────────────────────────────────────────┐
│                          CLIENT (Frontend)                           │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ HTTPS / JWT
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│          FastAPI — backend/app/modules/business_rules/               │
│                                                                      │
│   router.py       ← HTTP routing, input validation                   │
│   service.py      ← EaseCalculationService (orchestration)          │
│   engine.py       ← EaseEngine (pure calculation logic)             │
│   schemas.py      ← Pydantic request / response models              │
│   models.py       ← SQLAlchemy ORM models                           │
│   dependencies.py ← get_db, get_current_user, get_adjustment_or_404 │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
    raw_measurements      fabrics /        measurement_adjustments
    (Module 2 — R/O)   fabric_categories  (Module 5 — R/W)
                        (Module 3 — R/O)
```

Upstream (read-only):
- Module 2 → `raw_measurements` joined via `capture_sessions`
- Module 3 → `fabrics` joined via `fabric_categories` for elasticity data

Downstream:
- Module 7 reads `measurement_adjustments` directly from the shared DB.

---

## 2. Directory Layout

```
backend/app/modules/business_rules/
├── __init__.py
├── router.py          # FastAPI APIRouter — /adjustments endpoints
├── service.py         # EaseCalculationService — orchestration + DB I/O
├── engine.py          # EaseEngine — pure arithmetic, no DB access
├── schemas.py         # Pydantic I/O schemas
├── models.py          # SQLAlchemy ORM models
└── dependencies.py    # get_db, get_current_user, get_adjustment_or_404
```

> Note: Modules 5, 6, and 7 all live under `backend/app/modules/business_rules/`
> per the tech steering. Each module's files are prefixed or namespaced to avoid
> collisions (e.g., `engine.py` for M5, `compatibility.py` for M6, `report.py` for M7).

---

## 3. Database Schema

### 3.1 Table: `ease_rules` (reference / seed data)

```sql
CREATE TABLE ease_rules (
    elasticity_category  VARCHAR(30)   PRIMARY KEY,
    ease_delta_cm        DECIMAL(4,1)  NOT NULL,
    description          TEXT
);

INSERT INTO ease_rules (elasticity_category, ease_delta_cm, description) VALUES
    ('rigid',        4.0,  'Tissu non-élastique (ex. Pagne Wax) — aisance +4 cm'),
    ('semi-stretch', 2.0,  'Tissu légèrement élastique — aisance +2 cm'),
    ('stretch',     -2.0,  'Tissu très élastique (ex. Jersey) — aisance −2 cm');

COMMENT ON TABLE ease_rules IS
    'Reference table mapping fabric elasticity categories to ease delta values in cm.
     Read-only at runtime; modified only via migrations.';
```

### 3.2 Table: `measurement_adjustments`

```sql
CREATE TABLE measurement_adjustments (
    id                  UUID          PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Upstream references (read-only sources)
    session_id          UUID          NOT NULL
                        REFERENCES capture_sessions(id) ON DELETE CASCADE,
    fabric_id           UUID          NOT NULL,   -- FK to fabrics table (Module 3)

    -- Raw inputs (snapshot from raw_measurements at calculation time)
    raw_bust_cm         DECIMAL(5,1)  NOT NULL,
    raw_waist_cm        DECIMAL(5,1)  NOT NULL,
    raw_hips_cm         DECIMAL(5,1)  NOT NULL,

    -- Applied ease per zone (AC-03.1 — per-zone storage)
    bust_ease_cm        DECIMAL(4,1)  NOT NULL,
    waist_ease_cm       DECIMAL(4,1)  NOT NULL,
    hips_ease_cm        DECIMAL(4,1)  NOT NULL,

    -- Adjusted outputs
    adjusted_bust_cm    DECIMAL(5,1)  NOT NULL,
    adjusted_waist_cm   DECIMAL(5,1)  NOT NULL,
    adjusted_hips_cm    DECIMAL(5,1)  NOT NULL,

    -- Metadata
    ease_source         VARCHAR(30)   NOT NULL DEFAULT 'rule'
                        CHECK (ease_source IN ('rule', 'default_fallback')),
    calculated_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT now(),

    -- One adjustment per (session, fabric) pair — upsert target (AC-01.6)
    CONSTRAINT uq_adjustment_session_fabric UNIQUE (session_id, fabric_id)
);

COMMENT ON COLUMN measurement_adjustments.ease_source IS
    '''rule'' = applied from ease_rules table; ''default_fallback'' = unknown elasticity category.';

-- Auto-update updated_at (reuses the trigger function from Module 2 migration)
CREATE TRIGGER trg_measurement_adjustments_updated_at
    BEFORE UPDATE ON measurement_adjustments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- RLS: users see only adjustments on their own sessions (NFR-03)
ALTER TABLE measurement_adjustments ENABLE ROW LEVEL SECURITY;

CREATE POLICY adjustments_select_owner ON measurement_adjustments
    FOR SELECT USING (
        session_id IN (
            SELECT id FROM capture_sessions WHERE user_id = auth.uid()
        )
    );

CREATE POLICY adjustments_insert_owner ON measurement_adjustments
    FOR INSERT WITH CHECK (
        session_id IN (
            SELECT id FROM capture_sessions WHERE user_id = auth.uid()
        )
    );

CREATE POLICY adjustments_update_owner ON measurement_adjustments
    FOR UPDATE USING (
        session_id IN (
            SELECT id FROM capture_sessions WHERE user_id = auth.uid()
        )
    );
```

---

## 4. Pydantic Schemas (`schemas.py`)

```python
# ── Request ──────────────────────────────────────────────────────────

class AdjustmentRequest(BaseModel):
    session_id: UUID
    fabric_id:  UUID

# ── Nested detail ────────────────────────────────────────────────────

class ZoneDetail(BaseModel):
    """Raw + ease + adjusted value for one measurement zone."""
    raw_cm:      Decimal
    ease_cm:     Decimal
    adjusted_cm: Decimal

class AdjustmentResponse(BaseModel):
    """Full adjustment record — returned by POST (201/200) and GET by ID."""
    adjustment_id:     UUID
    session_id:        UUID
    fabric_id:         UUID
    fabric_name:       str
    elasticity_category: str | None    # None when ease_source == 'default_fallback'
    ease_source:       Literal["rule", "default_fallback"]
    bust:              ZoneDetail
    waist:             ZoneDetail
    hips:              ZoneDetail
    calculated_at:     datetime
    data_integrity_warning: bool = False   # AC-07.1

class AdjustmentSummary(BaseModel):
    """Lightweight item for list endpoint."""
    adjustment_id:       UUID
    fabric_id:           UUID
    fabric_name:         str
    elasticity_category: str | None
    ease_source:         str
    adjusted_bust_cm:    Decimal
    adjusted_waist_cm:   Decimal
    adjusted_hips_cm:    Decimal
    calculated_at:       datetime

class AdjustmentListResponse(BaseModel):
    adjustments: list[AdjustmentSummary]
    total:       int
```

---

## 5. API Endpoints

Base path: `/api/v1/ease`  
All endpoints require `Authorization: Bearer <JWT>`.

| Method | Path | Description | Success | Errors |
|---|---|---|---|---|
| `POST` | `/adjustments` | Compute (or recompute) an ease adjustment | 201 / 200 | 401, 403, 404, 424 |
| `GET` | `/adjustments/{adjustment_id}` | Retrieve a specific adjustment | 200 | 401, 403, 404 |
| `GET` | `/sessions/{session_id}/adjustments` | List all adjustments for a session | 200 | 401, 403, 404 |

### 5.1 POST `/adjustments`

Request body: `AdjustmentRequest`

Processing flow:
1. Verify JWT → extract `user_id`.
2. Load `capture_session` for `session_id`; assert `user_id` matches → 403/404.
3. Assert `session.status == 'success'` → 424 if not.
4. Load `raw_measurements` row for the session.
5. Load `fabric` + its `fabric_category` for `fabric_id` → 404 if not found.
6. Call `EaseEngine.compute()` with raw measurements + elasticity category.
7. Upsert into `measurement_adjustments` on `(session_id, fabric_id)`.
8. Return `AdjustmentResponse`:
   - HTTP **201** if a new record was created.
   - HTTP **200** if an existing record was overwritten (AC-01.6).

### 5.2 GET `/adjustments/{adjustment_id}`

- Loads `measurement_adjustment` by PK.
- Asserts caller owns the linked session → 403.
- Joins `fabric` for `fabric_name` and `elasticity_category`.
- Sets `data_integrity_warning = True` if the linked session's status is no longer
  `success` (AC-07.1).
- Returns `AdjustmentResponse`.

### 5.3 GET `/sessions/{session_id}/adjustments`

- Asserts caller owns the session → 403/404.
- Returns list of `AdjustmentSummary`, ordered by `calculated_at DESC`.
- Returns empty list if none exist (AC-06.2).

---

## 6. Ease Engine (`engine.py`)

### 6.1 Interface

```python
@dataclass
class EaseInput:
    bust_cm:              float
    waist_cm:             float
    hips_cm:              float
    elasticity_category:  str | None   # None → default fallback

@dataclass
class ZoneResult:
    raw_cm:      float
    ease_cm:     float
    adjusted_cm: float

@dataclass
class EaseOutput:
    bust:        ZoneResult
    waist:       ZoneResult
    hips:        ZoneResult
    ease_source: Literal["rule", "default_fallback"]
    warnings:    list[str]   # populated by floor / fallback rules
```

### 6.2 Ease Delta Resolution

```python
_EASE_RULES: dict[str, float] = {
    "rigid":        4.0,
    "semi-stretch": 2.0,
    "stretch":     -2.0,
}
_DEFAULT_EASE_CM: float = 3.0

def _resolve_delta(elasticity_category: str | None) -> tuple[float, str]:
    """
    Returns (delta_cm, ease_source).
    Falls back to _DEFAULT_EASE_CM when category is unknown/None.
    """
    if elasticity_category in _EASE_RULES:
        return _EASE_RULES[elasticity_category], "rule"
    return _DEFAULT_EASE_CM, "default_fallback"
```

### 6.3 Zone Calculation

```python
_FLOOR_CM:   float = 0.0    # AC-04.1 — hard arithmetic floor
_WARN_CM:    float = 30.0   # AC-04.2 — soft warning threshold

def _compute_zone(raw: float, delta: float) -> tuple[float, list[str]]:
    """
    Apply ease delta to one measurement zone.
    Returns (adjusted_cm, warnings).
    """
    adjusted = raw + delta
    warnings = []
    if adjusted < _FLOOR_CM:
        warnings.append(
            f"Valeur ajustée ({adjusted:.1f} cm) < 0 cm — plafonnée à 0.0 cm."
        )
        adjusted = _FLOOR_CM
    elif adjusted < _WARN_CM:
        warnings.append(
            f"Valeur ajustée ({adjusted:.1f} cm) < 30 cm — données d'entrée suspectes."
        )
    return round(adjusted, 1), warnings
```

### 6.4 Full Computation

```python
class EaseEngine:
    def compute(self, inp: EaseInput) -> EaseOutput:
        delta, ease_source = _resolve_delta(inp.elasticity_category)
        all_warnings: list[str] = []

        bust_adj,  bust_w  = _compute_zone(inp.bust_cm,  delta)
        waist_adj, waist_w = _compute_zone(inp.waist_cm, delta)
        hips_adj,  hips_w  = _compute_zone(inp.hips_cm,  delta)

        all_warnings.extend(bust_w + waist_w + hips_w)

        if ease_source == "default_fallback":
            all_warnings.append(
                f"Catégorie d'élasticité inconnue "
                f"({inp.elasticity_category!r}) — aisance par défaut +3 cm appliquée."
            )

        return EaseOutput(
            bust=ZoneResult(inp.bust_cm,  delta, bust_adj),
            waist=ZoneResult(inp.waist_cm, delta, waist_adj),
            hips=ZoneResult(inp.hips_cm,  delta, hips_adj),
            ease_source=ease_source,
            warnings=all_warnings,
        )
```

---

## 7. Service Layer (`service.py`)

```python
class EaseCalculationService:

    async def compute_adjustment(
        self,
        user_id:    UUID,
        session_id: UUID,
        fabric_id:  UUID,
        db:         AsyncSession,
    ) -> tuple[MeasurementAdjustment, bool]:
        """
        Returns (adjustment_orm_object, is_new_record).
        Raises HTTPException on all guard failures.
        """
        # Guard 1 — session ownership (AC-01.2)
        session = await _load_session_or_raise(session_id, user_id, db)

        # Guard 2 — session has completed measurement (AC-01.3)
        raw = await _load_raw_measurement_or_raise(session_id, db)

        # Guard 3 — fabric exists (AC-01.4)
        fabric, category = await _load_fabric_or_raise(fabric_id, db)

        # Calculate
        engine = EaseEngine()
        output = engine.compute(EaseInput(
            bust_cm=float(raw.bust_cm),
            waist_cm=float(raw.waist_cm),
            hips_cm=float(raw.hips_cm),
            elasticity_category=category,
        ))

        # Log warnings (AC-02.4, AC-04.1, AC-04.2)
        for w in output.warnings:
            logger.warning("EaseEngine [session=%s fabric=%s]: %s", session_id, fabric_id, w)

        # Upsert (AC-01.6)
        adjustment, is_new = await _upsert_adjustment(
            session_id, fabric_id, raw, output, db
        )
        return adjustment, is_new
```

---

## 8. Data Access Patterns

### Reading Module 2 data (read-only)

```sql
-- Load raw measurements for a session
SELECT rm.bust_cm, rm.waist_cm, rm.hips_cm
FROM raw_measurements rm
JOIN capture_sessions cs ON cs.id = rm.session_id
WHERE cs.id      = :session_id
  AND cs.user_id = :user_id
  AND cs.status  = 'success';
```

### Reading Module 3 data (read-only)

Module 3's table structure (from `docs/data-models/module_3_fabric_catalog.md`):

```sql
-- Load fabric + its elasticity category
SELECT
    f.id          AS fabric_id,
    f.fabric_name,
    fc.reference_rigidity_level AS elasticity_category
FROM fabrics f
JOIN fabric_categories fc ON fc.id = f.category_id
WHERE f.id = :fabric_id;
```

> **Note to Module 3 owner:** Module 5 reads `fabrics.id`, `fabrics.fabric_name`,
> and `fabric_categories.reference_rigidity_level`. These column names must be
> stable; any rename requires a coordinated update here.

### Upsert pattern

```sql
INSERT INTO measurement_adjustments (
    id, session_id, fabric_id,
    raw_bust_cm, raw_waist_cm, raw_hips_cm,
    bust_ease_cm, waist_ease_cm, hips_ease_cm,
    adjusted_bust_cm, adjusted_waist_cm, adjusted_hips_cm,
    ease_source, calculated_at, updated_at
) VALUES (...)
ON CONFLICT (session_id, fabric_id)
DO UPDATE SET
    raw_bust_cm       = EXCLUDED.raw_bust_cm,
    raw_waist_cm      = EXCLUDED.raw_waist_cm,
    raw_hips_cm       = EXCLUDED.raw_hips_cm,
    bust_ease_cm      = EXCLUDED.bust_ease_cm,
    waist_ease_cm     = EXCLUDED.waist_ease_cm,
    hips_ease_cm      = EXCLUDED.hips_ease_cm,
    adjusted_bust_cm  = EXCLUDED.adjusted_bust_cm,
    adjusted_waist_cm = EXCLUDED.adjusted_waist_cm,
    adjusted_hips_cm  = EXCLUDED.adjusted_hips_cm,
    ease_source       = EXCLUDED.ease_source,
    updated_at        = now();
```

---

## 9. Error Response Envelope

All HTTP errors follow the Module 2 convention:

```json
{ "detail": "<human-readable message in French>" }
```

| HTTP | Condition |
|---|---|
| 401 | Missing or invalid Bearer JWT |
| 403 | Session or adjustment belongs to a different user |
| 404 | `session_id` or `fabric_id` not found |
| 424 | Session exists but has no completed raw measurement |

---

## 10. Inter-Module Contracts

### Input from Module 2

Module 5 reads `raw_measurements` directly from the shared Supabase DB (read-only).
See Module 2 `design.md §12` for the canonical SQL query.

### Input from Module 3

Module 5 reads `fabrics` and `fabric_categories` directly from the shared Supabase DB (read-only).
The critical field is `fabric_categories.reference_rigidity_level` which must hold one of
`rigid`, `semi-stretch`, or `stretch`.

### Output to Module 7 (Final Report)

Module 7 reads `measurement_adjustments` directly from the shared DB:

```sql
-- Retrieve all adjustments for a user's active session
SELECT
    ma.id            AS adjustment_id,
    ma.session_id,
    ma.fabric_id,
    ma.adjusted_bust_cm,
    ma.adjusted_waist_cm,
    ma.adjusted_hips_cm,
    ma.bust_ease_cm,
    ma.waist_ease_cm,
    ma.hips_ease_cm,
    ma.ease_source,
    ma.calculated_at
FROM measurement_adjustments ma
JOIN capture_sessions cs ON cs.id = ma.session_id
WHERE cs.user_id   = :user_id
  AND cs.is_active = true
ORDER BY ma.calculated_at DESC;
```

**Table ownership:** Module 5 is the **sole writer** of `measurement_adjustments`.
Modules 6 and 7 are **read-only** consumers.

---

## 11. Logging Strategy

All warning-level events are emitted via Python's `logging` module at level `WARNING`
with a structured format to facilitate admin monitoring:

| Event | Log message pattern |
|---|---|
| Unknown elasticity | `EaseEngine [session=<id> fabric=<id>]: Catégorie d'élasticité inconnue ('<val>') — aisance par défaut +3 cm appliquée.` |
| Adjusted value clamped to 0 | `EaseEngine [session=<id> fabric=<id>]: Valeur ajustée (<val> cm) < 0 cm — plafonnée à 0.0 cm.` |
| Adjusted value below 30 cm | `EaseEngine [session=<id> fabric=<id>]: Valeur ajustée (<val> cm) < 30 cm — données d'entrée suspectes.` |
