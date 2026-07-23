# Module 5 — Ease Allowance Calculation Engine
# (Moteur de calcul d'aisance)

## Purpose

This module converts raw anatomical measurements (produced by Module 2) into
final garment-cutting dimensions by applying a fabric-specific ease allowance.
It evaluates the physical elasticity of a selected fabric and adds or subtracts
centimetres to ensure the finished garment is comfortable and wearable.

Results are persisted as `measurement_adjustments` records (one per
session + fabric pair) and consumed by:
- **Module 7** — Final Result / Report (reads `measurement_adjustments` directly)

---

## Directory layout

```
backend/app/modules/business_rules/
├── __init__.py         Package marker (shared by M5, M6, M7)
├── router.py           FastAPI APIRouter — 3 endpoints at /api/v1/ease
├── service.py          EaseCalculationService — orchestration + DB I/O
├── engine.py           EaseEngine — pure arithmetic, zero DB access
├── schemas.py          Pydantic request / response models
├── models.py           SQLAlchemy ORM models (EaseRule, MeasurementAdjustment)
└── dependencies.py     get_db, get_current_user, get_adjustment_or_404
```

---

## API endpoints

All endpoints mounted at `/api/v1/ease` and require `Authorization: Bearer <JWT>`.

| Method | Path | Description | Success | Key errors |
|---|---|---|---|---|
| `POST` | `/adjustments` | Compute (or recompute) an ease adjustment | 201 / 200 | 401, 403, 404, 424 |
| `GET` | `/adjustments/{adjustment_id}` | Retrieve a specific adjustment | 200 | 401, 403, 404 |
| `GET` | `/sessions/{session_id}/adjustments` | List all adjustments for a session | 200 | 401, 403, 404 |

Interactive documentation available at `/docs` when the server is running.

---

## Ease rules

| Elasticity category | Ease delta | Example fabric |
|---|---|---|
| `rigid` | +4.0 cm | Pagne Wax |
| `semi-stretch` | +2.0 cm | Popeline légère |
| `stretch` | −2.0 cm | Jersey |
| *(unknown / missing)* | +3.0 cm | *(default fallback — WARNING logged)* |

Rules are seeded by migration `005_create_ease_rules.sql` and are read-only at runtime.

---

## Key business rules

- **Uniform ease by default:** The same delta is applied to bust, waist, and hips.
  Per-zone ease values are stored individually (`bust_ease_cm`, `waist_ease_cm`,
  `hips_ease_cm`) to support future per-zone overrides without a schema migration.
- **Floor constraint:** Adjusted measurements are clamped to a minimum of `0.0 cm`.
  A WARNING is logged if any adjusted value is > 0 cm but < 30 cm (suspect CV data).
- **Default fallback:** When `elasticity_category` is absent or unrecognised, `+3.0 cm`
  is applied, `ease_source` is set to `"default_fallback"`, and a WARNING is emitted.
  The user request is never blocked.
- **Upsert semantics:** Re-submitting the same `(session_id, fabric_id)` pair
  overwrites the existing adjustment (HTTP 200) instead of creating a duplicate.
- **Prerequisite:** The session must have `status = 'success'` in Module 2 (i.e., a
  completed `raw_measurements` row must exist) — otherwise HTTP 424 is returned.

---

## Database tables

| Table | Purpose |
|---|---|
| `ease_rules` | Reference table — elasticity category → ease delta (seeded, read-only) |
| `measurement_adjustments` | One row per (session, fabric) pair; stores raw + ease + adjusted values |

Both tables have Row Level Security enabled — users can only access adjustments
linked to their own capture sessions.

Migration files are in `backend/migrations/` — run in order:
```
005_create_ease_rules.sql           ← run first
006_create_measurement_adjustments.sql
```

---

## Environment variables

No new environment variables are required for Module 5.
It reuses all variables already present for Module 2:

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_KEY` | Yes | Supabase anon or service-role key |
| `SUPABASE_JWT_SECRET` | Yes | JWT secret for Bearer token verification |

---

## Running the server

```bash
cd backend
uvicorn main:app --reload --port 8000
```

Health check: `GET /health` → `{"status": "ok"}`

---

## Smoke tests

See `docs/modules/module5_smoke_tests.md` for a step-by-step curl-based test guide
covering all 7 scenarios (happy path, upsert, all three categories, fallback,
424 guard, multi-fabric list, cross-user isolation).

---

## Inter-module contracts

### Input from Module 2 (`raw_measurements`)

Module 5 reads `bust_cm`, `waist_cm`, `hips_cm` from `raw_measurements` joined
via `capture_sessions`. See `design.md §8` for the canonical SQL query.

### Input from Module 3 (`fabrics` + `fabric_categories`)

Module 5 reads `fabrics.fabric_name` and `fabric_categories.reference_rigidity_level`.
These column names must remain stable — coordinate with the Module 3 owner before renaming.

### Output to Module 7

Module 7 reads `measurement_adjustments` directly:

```sql
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

**Table ownership:** Module 5 is the sole writer of `measurement_adjustments`.
Modules 6 and 7 are read-only consumers.

---

## Spec reference

| Artefact | Path |
|---|---|
| Requirements | `.kiro/specs/moteur-aisance/requirements.md` |
| Design | `.kiro/specs/moteur-aisance/design.md` |
| Tasks | `.kiro/specs/moteur-aisance/tasks.md` |
| Functional doc | `docs/modules/MODULE_5_calculation_engine.md` |
| Data model | `docs/data-models/module5_fabric_measurement_adjustment.md` |
| Smoke tests | `docs/modules/module5_smoke_tests.md` |
