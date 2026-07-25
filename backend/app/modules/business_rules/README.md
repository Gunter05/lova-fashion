# Business Rules — Modules 5, 6 & 7

## Module 5 — Ease Allowance Calculation Engine

Computes adjusted garment-cutting dimensions from raw body measurements and a chosen fabric's elasticity. Sole writer of `measurement_adjustments`.

Endpoints: `POST /api/v1/adjustments` · `GET /api/v1/adjustments/{id}` · `GET /api/v1/sessions/{id}/adjustments`

---

## Module 7 — Final Result & Report (Synthesis)

### Overview

Module 7 is the terminal aggregation layer. It subscribes to the `compatibility.evaluated` EventBus event published by Module 6, creates an immutable `Rapport_mesure` record, and publishes `report.saved` to Module 1's profile archival handler.

### Event-Driven Creation Flow

```
Module 6 publishes "compatibility.evaluated"
    │
    ▼
make_compatibility_evaluated_handler (report_handler.py)
    │
    ├─ 1. Parse CompatibilityEvaluatedEvent (Pydantic validation)
    ├─ 2. Guard: CNI exists in users table
    ├─ 3. Guard: adjustment_id exists in measurement_adjustments
    ├─ 4. Guard: adjusted measurements are non-negative
    ├─ 5. Guard: fabric_id exists in fabrics table
    ├─ 6. Guard: model_id exists in models table
    ├─ 7. Snapshot Module 5 data → INSERT rapport_mesure (always INSERT, never UPSERT)
    └─ 8. Publish "report.saved" (fire-and-forget → Module 1 archives the reference)
```

Any guard failure logs an ERROR and discards the event — no DB write.

### HTTP Endpoints

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `/api/v1/reports/me` | Client | Own report history (newest first) |
| GET | `/api/v1/reports/client/{cni}` | Tailor, Admin | Reports for a specific client |
| GET | `/api/v1/reports/{report_id}` | Client (owner), Tailor, Admin | Full report detail |

All endpoints read `x-user-cni` and `x-user-role` headers set by Module 1's JWT middleware.
No POST/PUT/PATCH/DELETE routes — creation is event-driven only.

### Table Ownership

| Table | Owner | Read-only consumers |
|-------|-------|---------------------|
| `measurement_adjustments` | Module 5 | Modules 6, 7 |
| `rapport_mesure` | **Module 7** | Module 1 (via `report.saved` event), Frontend (via API) |

### `report.saved` Event Contract (for Module 1)

```json
{
  "type":            "report.saved",
  "cni":             "<9-char CNI string>",
  "report_id":       "<UUID as plain string>",
  "date_generation": "<ISO 8601 UTC timestamp string>"
}
```

This payload must match exactly what `handle_report_saved` in `app/modules/auth_user_profile/events/handlers.py` expects.

### Files

| File | Purpose |
|------|---------|
| `report_models.py` | SQLAlchemy ORM — `RapportMesure` |
| `report_schemas.py` | Pydantic schemas — event payloads + API responses |
| `report_service.py` | `ReportService` + pure helpers (`build_display_hints`, guards) |
| `report_handler.py` | EventBus handler factory for `compatibility.evaluated` |
| `report_router.py` | FastAPI APIRouter — three GET endpoints |
| `../../db/migrations/007_module7_rapport_mesure.sql` | DDL migration |
