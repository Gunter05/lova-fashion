# Design Document — Module 7: Final Result & Report (Synthesis)

## Overview

Module 7 is the terminal synthesis layer of the Lova Fashion backend. It subscribes to the
`compatibility.evaluated` EventBus event published by Module 6, validates all upstream data,
creates an immutable `Rapport_mesure` record in PostgreSQL, and publishes `report.saved` to
notify Module 1's profile archival handler. Three read-only HTTP endpoints allow clients,
tailors, and admins to retrieve reports and report history.

All Module 7 files live inside `backend/app/modules/business_rules/` alongside the existing
Module 5 files, using a `report_` prefix to avoid naming collisions.

---

## Architecture

### Module Position in the System

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         EventBus (in-process singleton)                      │
│   compatibility.evaluated ─────────────────────────────► Module 7            │
│   report.saved            ◄────────────────────────────── Module 7            │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│                    CLIENT (Frontend — React + Tailwind CSS)                  │
└────────────────────────────────────┬─────────────────────────────────────────┘
                                     │ HTTPS / JWT
                                     ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│          FastAPI — backend/app/modules/business_rules/                       │
│                                                                              │
│   report_router.py    ← HTTP routing, input validation                       │
│   report_service.py   ← ReportService + build_display_hints()               │
│   report_schemas.py   ← Pydantic request / response models                  │
│   report_models.py    ← SQLAlchemy ORM — RapportMesure                      │
│   report_handler.py   ← EventBus subscriber for compatibility.evaluated     │
└──────────────┬──────────────────────┬─────────────────────────┬─────────────┘
               │                      │                         │
               ▼                      ▼                         ▼
  measurement_adjustments          fabrics /               models
  (Module 5 — R/O)              fabric_categories       (Module 4 — R/O)
                                 (Module 3 — R/O)
               │
               ▼
         rapport_mesure
         (Module 7 — R/W, sole owner)
```

Upstream reads (read-only):
- Module 5 → `measurement_adjustments` (adjusted measurements snapshot)
- Module 3 → `fabrics` (existence check)
- Module 4 → `models` (existence check)
- Module 1 → `users` (CNI existence check)

Downstream writes:
- Module 7 → `rapport_mesure` (sole owner, no other module writes here)
- Module 7 → EventBus `report.saved` → consumed by Module 1

### Directory Layout

```
backend/app/modules/business_rules/
├── __init__.py
├── router.py              # Module 5 (ease) — pre-existing
├── service.py             # Module 5 — pre-existing
├── engine.py              # Module 5 — pre-existing
├── schemas.py             # Module 5 — pre-existing
├── models.py              # Module 5 — pre-existing
├── dependencies.py        # Module 5 / shared — pre-existing
│
├── report_handler.py      # [Module 7] EventBus handler for compatibility.evaluated
├── report_service.py      # [Module 7] ReportService — orchestration + DB I/O
├── report_schemas.py      # [Module 7] Pydantic I/O schemas
├── report_models.py       # [Module 7] SQLAlchemy ORM — RapportMesure
└── report_router.py       # [Module 7] FastAPI APIRouter — /reports endpoints
```

---

## Components and Interfaces

### Event Handler (`report_handler.py`)

The factory function `make_compatibility_evaluated_handler(session_factory)` returns a
coroutine that is registered on the EventBus at application startup (in `main.py` lifespan).

```python
def make_compatibility_evaluated_handler(session_factory):
    service = ReportService()

    async def handle_compatibility_evaluated(payload: dict) -> None:
        # 1. Parse + validate payload with CompatibilityEvaluatedEvent (Pydantic)
        #    → log ERROR + return on parse failure
        # 2. Open DB session, call service.create_report_from_event()
        #    → log ERROR + return on any service exception
        # 3. Publish report.saved to EventBus (fire-and-forget)
        #    → log WARNING on EventBus exception, do NOT re-raise

    return handle_compatibility_evaluated
```

### Service Layer (`report_service.py`)

**Pure helper** — no DB access:
```python
def build_display_hints(verdict: str, incompatible_zones: list | None) -> DisplayHints
```
Maps `"compatible"` → `"green"`, `"minor_adjustments"` → `"orange"`, `"incompatible"` → `"red"`.
Populates `highlight_zones` from zone names when `verdict == "incompatible"`.

**`ReportService` methods:**

| Method | Description |
|---|---|
| `create_report_from_event(event, db)` | Validates all guards, snapshots measurements, INSERTs a new `RapportMesure`, returns ORM object |
| `get_report(report_id, caller_cni, caller_role, db)` | Loads by PK, enforces client ownership, allows tailor/admin |
| `list_reports_for_client(cni, db)` | Returns all reports for the CNI ordered `generated_at DESC` |
| `list_reports_for_client_as_tailor(target_cni, db)` | Checks user existence, delegates to `list_reports_for_client` |

**Private helpers:**

| Helper | Purpose |
|---|---|
| `_assert_user_exists(cni, db)` | Raises `ReportCreationError` if CNI not in `users` |
| `_load_adjustment_or_raise(adjustment_id, db)` | Raises `ReportCreationError` if adjustment missing |
| `_validate_measurements(adjustment)` | Raises `ReportCreationError` if any adjusted value < 0 or NULL |
| `_assert_fabric_exists(fabric_id, db)` | Raises `ReportCreationError` if fabric missing |
| `_assert_model_exists(model_id, db)` | Raises `ReportCreationError` if model missing |
| `_build_snapshot(adjustment) → dict` | Returns the 7-field JSONB snapshot dict |
| `_load_report_or_404(report_id, db)` | Raises HTTP 404 if report not found |
| `_query_reports_by_cni(cni, db)` | SELECT all reports for CNI, ORDER BY generated_at DESC |

### HTTP Router (`report_router.py`)

Base path: `/api/v1/reports` | Tag: `reports` | All endpoints: Bearer JWT required

| Method | Path | Roles | Description |
|---|---|---|---|
| `GET` | `/reports/{report_id}` | Client (owner), Tailor, Admin | Retrieve a specific report |
| `GET` | `/reports/me` | Client | List all reports for the authenticated client |
| `GET` | `/reports/client/{cni}` | Tailor, Admin | List all reports for a specific client |

No POST/PUT/PATCH/DELETE routes — creation is event-driven only.

### Registration in `main.py`

```python
# lifespan — subscribe event handler
from app.modules.business_rules.report_handler import make_compatibility_evaluated_handler
event_bus.subscribe(
    "compatibility.evaluated",
    make_compatibility_evaluated_handler(AsyncSessionLocal),
)

# Router mount
from app.modules.business_rules.report_router import router as report_router
app.include_router(report_router, prefix="/api/v1")
```

---

## Data Models

### `rapport_mesure` Table (DDL)

```sql
CREATE TABLE rapport_mesure (
    id_report             UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    cni                   VARCHAR(9)    NOT NULL
                          REFERENCES users(cni) ON DELETE RESTRICT,
    adjustment_id         UUID          NOT NULL
                          REFERENCES measurement_adjustments(id) ON DELETE RESTRICT,
    fabric_id             UUID          NOT NULL
                          REFERENCES fabrics(fabric_id) ON DELETE RESTRICT,
    model_id              UUID          NOT NULL
                          REFERENCES models(model_id) ON DELETE RESTRICT,
    verdict               VARCHAR(30)   NOT NULL
                          CHECK (verdict IN ('compatible', 'incompatible', 'minor_adjustments')),
    adjusted_measurements JSONB         NOT NULL,
    advice                TEXT          NOT NULL,
    incompatible_zones    JSONB         NULL,
    generated_at          TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX idx_rapport_mesure_cni_generated
    ON rapport_mesure (cni, generated_at DESC);

ALTER TABLE rapport_mesure ENABLE ROW LEVEL SECURITY;

CREATE POLICY rapport_select_owner ON rapport_mesure
    FOR SELECT USING (cni = current_setting('app.current_user_cni', true));
-- No UPDATE or DELETE policies — immutability at DB level (NFR-03)
```

### `adjusted_measurements` JSONB Structure

```json
{
  "adjusted_bust_cm":  88.0,
  "adjusted_waist_cm": 70.0,
  "adjusted_hips_cm":  94.0,
  "bust_ease_cm":       4.0,
  "waist_ease_cm":      4.0,
  "hips_ease_cm":       4.0,
  "ease_source":       "rule"
}
```

### `incompatible_zones` JSONB Structure (verdict = `"incompatible"` only)

```json
[
  {"zone": "bust",  "reason": "Fabric too rigid for fitted model"},
  {"zone": "waist", "reason": "Insufficient stretch margin"}
]
```

### SQLAlchemy ORM Model (`report_models.py`)

```python
class RapportMesure(Base):
    __tablename__ = "rapport_mesure"

    id_report:             UUID PK, default=uuid4
    cni:                   VARCHAR(9), FK → users.cni, NOT NULL
    adjustment_id:         UUID, FK → measurement_adjustments.id, NOT NULL
    fabric_id:             UUID, FK → fabrics.fabric_id, NOT NULL
    model_id:              UUID, FK → models.model_id, NOT NULL
    verdict:               VARCHAR(30), CHECK constraint, NOT NULL
    adjusted_measurements: JSONB, NOT NULL
    advice:                TEXT, NOT NULL
    incompatible_zones:    JSONB, NULL
    generated_at:          TIMESTAMPTZ, server_default=now()

    __table_args__: CheckConstraint on verdict, Index on (cni, generated_at DESC)
```

### Pydantic Schemas (`report_schemas.py`)

```python
class IncompatibleZoneItem(BaseModel):
    zone: str
    reason: str

class CompatibilityEvaluatedEvent(BaseModel):
    type: Literal["compatibility.evaluated"]
    emitted_at: datetime
    cni: str                  # min_length=9, max_length=9
    adjustment_id: UUID
    fabric_id: UUID
    model_id: UUID
    verdict: Literal["compatible", "incompatible", "minor_adjustments"]
    advice: str
    incompatible_zones: Optional[list[IncompatibleZoneItem]] = None

class AdjustedMeasurementsSnapshot(BaseModel):
    adjusted_bust_cm: float
    adjusted_waist_cm: float
    adjusted_hips_cm: float
    bust_ease_cm: float
    waist_ease_cm: float
    hips_ease_cm: float
    ease_source: str

class DisplayHints(BaseModel):
    verdict_color: Literal["green", "orange", "red"]
    highlight_zones: list[str]

class ReportResponse(BaseModel):
    report_id: UUID
    cni: str
    adjustment_id: UUID
    fabric_id: UUID
    model_id: UUID
    verdict: Literal["compatible", "incompatible", "minor_adjustments"]
    advice: str
    adjusted_measurements: AdjustedMeasurementsSnapshot
    incompatible_zones: Optional[list[IncompatibleZoneItem]] = None
    display_hints: DisplayHints
    generated_at: datetime

class ReportSummary(BaseModel):
    report_id: UUID
    verdict: Literal["compatible", "incompatible", "minor_adjustments"]
    verdict_color: Literal["green", "orange", "red"]
    fabric_id: UUID
    model_id: UUID
    generated_at: datetime

class ReportListResponse(BaseModel):
    reports: list[ReportSummary]
    total: int

class ReportSavedEvent(BaseModel):
    type: Literal["report.saved"] = "report.saved"
    cni: str
    report_id: str        # UUID as string — Module 1 handler expects str
    date_generation: str  # ISO 8601 UTC — Module 1 handler expects str
```

---

## Error Handling

| Condition | Scope | HTTP / Level | Report created? |
|---|---|---|---|
| Invalid `compatibility.evaluated` payload | Event handler | ERROR log | No |
| `adjustment_id` not found | Event handler | ERROR log | No |
| Adjusted measurement negative or NULL | Event handler | ERROR log | No |
| `fabric_id` not found | Event handler | ERROR log | No |
| `model_id` not found | Event handler | ERROR log | No |
| `cni` not found in `users` | Event handler | ERROR log | No |
| Invalid `verdict` value | Event handler | ERROR log | No |
| EventBus publish failure (`report.saved`) | Event handler | WARNING log | **Yes** (already committed) |
| Report not found (`GET /reports/{id}`) | HTTP | 404 | — |
| Client accessing another client's report | HTTP | 403 | — |
| Client calling `/reports/client/{cni}` | HTTP | 403 | — |
| Target CNI not found (`/reports/client/{cni}`) | HTTP | 404 | — |
| Missing / invalid Bearer JWT | HTTP | 401 | — |

All HTTP error responses follow the `{"detail": "<message>"}` envelope (NFR-05).

### Logging Patterns

| Event | Pattern |
|---|---|
| Invalid event payload | `Module 7: invalid compatibility.evaluated payload — <exc> | payload=<raw>` |
| Missing adjustment | `Module 7: adjustment_id=<id> not found for cni=<cni>` |
| Corrupt measurement | `Module 7: corrupt measurement in adjustment_id=<id> — zone=<zone> value=<val>` |
| Missing fabric | `Module 7: fabric_id=<id> not found for cni=<cni>` |
| Missing model | `Module 7: model_id=<id> not found for cni=<cni>` |
| Missing user | `Module 7: cni=<cni> not found in users table` |
| Invalid verdict | `Module 7: invalid verdict '<val>' in event for cni=<cni>` |
| EventBus publish fail | `Module 7: failed to publish report.saved for report_id=<id> — <exc>` |

---

## Correctness Properties

The following properties capture the invariants that should hold across all valid inputs
and are suitable candidates for property-based tests with Hypothesis.

### Property 1: Display Hints Color Coverage

For all valid verdict strings (`"compatible"`, `"minor_adjustments"`, `"incompatible"`),
`build_display_hints()` always returns a `verdict_color` that is one of
`{"green", "orange", "red"}` — the set is exhaustive and never returns `None` or an
unexpected value.

**Validates: Requirements 3.1, 3.2, 3.3**

### Property 2: highlight_zones Empty for Non-Incompatible Verdicts

For verdict values `"compatible"` and `"minor_adjustments"`, `build_display_hints()`
always returns `highlight_zones = []`, regardless of the content of `incompatible_zones`.

**Validates: Requirements 3.1, 3.2**

### Property 3: highlight_zones Length Matches incompatible_zones Length

When `verdict == "incompatible"` and `incompatible_zones` is a non-empty list,
`len(display_hints.highlight_zones) == len(incompatible_zones)`.

**Validates: Requirements 3.3**

### Property 4: AdjustedMeasurementsSnapshot Round-Trip

For any valid snapshot dict, serialising to JSON and parsing back through
`AdjustedMeasurementsSnapshot` produces a structurally identical object
(`decode(encode(x)) == x`).

**Validates: Requirements 2.1**

### Property 5: Measurement Validation Error Condition

For any set of three adjusted measurement values where at least one is < 0,
`_validate_measurements()` always raises `ReportCreationError`.
For any set where all three are >= 0, it never raises.

**Validates: Requirements 2.3**

### Property 6: Report List Ordering Invariant

For N reports belonging to the same CNI, `list_reports_for_client()` returns them
in non-increasing `generated_at` order:
`items[i].generated_at >= items[i+1].generated_at` for all adjacent pairs.

**Validates: Requirements 6.1**

---

## Testing Strategy

### Unit Tests

- `build_display_hints()` — all three verdict values, incompatible with multiple zones
- `_validate_measurements()` — valid, negative, NULL inputs
- `CompatibilityEvaluatedEvent` Pydantic schema — valid payloads, invalid verdict, CNI length
- `ReportSavedEvent` schema — field names match Module 1's contract exactly

### Integration Tests

- `GET /reports/{report_id}` — owner access, cross-client 403, tailor access, 404, 401
- `GET /reports/me` — list with reports, empty list
- `GET /reports/client/{cni}` — tailor access, client 403, unknown CNI 404
- Event handler happy path — one report row inserted, `report.saved` published
- Event handler error paths — missing adjustment, negative measurement, missing fabric
- EventBus failure — report committed, WARNING logged, no exception propagated
- Immutability — two events → two distinct rows

### Property-Based Tests (Hypothesis)

- `build_display_hints()` — color coverage, `highlight_zones` emptiness, length match
- `AdjustedMeasurementsSnapshot` round-trip serialisation
- `_validate_measurements()` — error condition property
- Report list ordering invariant

### Inter-Module Contract Tests

- Verify `report.saved` payload field names and types against Module 1's
  `handle_report_saved` handler signature in `auth_user_profile/events/handlers.py`

---

## Inter-Module Data Contracts

### Input from Module 5 (read-only snapshot)

```sql
SELECT id, adjusted_bust_cm, adjusted_waist_cm, adjusted_hips_cm,
       bust_ease_cm, waist_ease_cm, hips_ease_cm, ease_source
FROM measurement_adjustments
WHERE id = :adjustment_id;
```

Module 5 is the sole writer of `measurement_adjustments`. Module 7 reads once and snapshots.

### Input from Module 3 (existence check)

```sql
SELECT fabric_id FROM fabrics WHERE fabric_id = :fabric_id;
```

### Input from Module 4 (existence check)

```sql
SELECT model_id FROM models WHERE model_id = :model_id;
```

### Input from Module 1 (existence check)

```sql
SELECT cni FROM users WHERE cni = :cni;
```

### Output to Module 1 (EventBus `report.saved`)

```json
{
  "type": "report.saved",
  "cni": "<9-char CNI string>",
  "report_id": "<UUID as string>",
  "date_generation": "<ISO 8601 UTC timestamp string>"
}
```

This payload must match exactly what `handle_report_saved(AsyncSessionLocal)` in
`backend/app/modules/auth_user_profile/events/handlers.py` expects.

### Table Ownership

| Table | Owner | Read-only consumers |
|---|---|---|
| `measurement_adjustments` | Module 5 | Modules 6, 7 |
| `rapport_mesure` | **Module 7** | Module 1 (via event), Frontend (via API) |
