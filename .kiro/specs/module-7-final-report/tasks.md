# Implementation Plan: Module 7 — Final Result & Report (Synthesis)

## Overview

This plan implements Module 7 in eight sequential phases: scaffolding, database migration,
ORM + schemas, service logic, event handler, HTTP router, tests (unit + integration), and
property-based tests. Each task references the requirement acceptance criteria it satisfies
and the design section it corresponds to.

All source files live under `backend/app/modules/business_rules/` with a `report_` prefix.
Tests live under `backend/tests/business_rules/`.

---

## Tasks

### Phase 0 — Scaffolding

- [x] 1. Create the five new Module 7 source files inside `backend/app/modules/business_rules/`: `report_models.py`, `report_schemas.py`, `report_service.py`, `report_handler.py`, `report_router.py`. Each file starts with a module-level docstring describing its role. _Design §Architecture / Directory Layout_

- [x] 2. Register `report_router` in `backend/main.py`: import `router as report_router` from `app.modules.business_rules.report_router` and call `app.include_router(report_router, prefix="/api/v1")`. _Design §Components and Interfaces / Registration in main.py_

- [x] 3. Register the `compatibility.evaluated` handler in the `lifespan` async context manager in `backend/main.py`: `event_bus.subscribe("compatibility.evaluated", make_compatibility_evaluated_handler(AsyncSessionLocal))`. _Req 1 AC1 · Design §Components and Interfaces_

### Phase 1 — Database Migration

- [x] 4. Write and execute the SQL migration for the `rapport_mesure` table: all columns (`id_report` UUID PK with `gen_random_uuid()`, `cni` FK → users, `adjustment_id` FK → measurement_adjustments, `fabric_id` FK → fabrics, `model_id` FK → models, `verdict` CHECK constraint, `adjusted_measurements` JSONB NOT NULL, `advice` TEXT NOT NULL, `incompatible_zones` JSONB NULL, `generated_at` TIMESTAMPTZ DEFAULT now()). _Req 1 AC1, AC3, AC5; Req 8 AC1; NFR-03, NFR-06 · Design §Data Models_

- [x] 5. Add composite index `idx_rapport_mesure_cni_generated` on `(cni, generated_at DESC)` to support efficient client history queries. _Req 6 AC1 · Design §Data Models_

- [x] 6. Enable RLS on `rapport_mesure` and add the SELECT policy `rapport_select_owner` scoped to `current_setting('app.current_user_cni', true)`. Do NOT create UPDATE or DELETE policies (immutability at DB level, NFR-03). _Req 8 AC1; NFR-03 · Design §Data Models_

### Phase 2 — ORM Model & Pydantic Schemas

- [x] 7. Implement `RapportMesure` SQLAlchemy ORM class in `report_models.py`: map all columns, include `CheckConstraint` for `verdict`, and add the composite `Index` on `(cni, generated_at)`. _Design §Data Models_

- [x] 8. Implement all Pydantic schemas in `report_schemas.py`: `IncompatibleZoneItem`, `CompatibilityEvaluatedEvent` (with `verdict` Literal and CNI length validation), `AdjustedMeasurementsSnapshot`, `DisplayHints`, `ReportResponse`, `ReportSummary`, `ReportListResponse`, `ReportSavedEvent`. _Req 3 AC5; Req 5 AC1; Req 6 AC3; Req 9 AC2 · Design §Data Models_

### Phase 3 — Service Logic

- [x] 9. Implement `build_display_hints(verdict, incompatible_zones) -> DisplayHints` as a pure module-level function in `report_service.py`: map `"compatible"` → `"green"`, `"minor_adjustments"` → `"orange"`, `"incompatible"` → `"red"`; populate `highlight_zones` from zone names when verdict is `"incompatible"`, empty list otherwise. _Req 3 AC1–3 · Design §Components and Interfaces_

- [x] 10. Implement `_assert_user_exists(cni, db)` helper in `report_service.py`: query `users WHERE cni = :cni`; raise `ReportCreationError` if not found. _Req 4 AC3 · Design §Components and Interfaces_

- [x] 11. Implement `_load_adjustment_or_raise(adjustment_id, db)` helper: query `measurement_adjustments WHERE id = :adjustment_id`; raise `ReportCreationError` if not found. _Req 2 AC2 · Design §Components and Interfaces_

- [x] 12. Implement `_validate_measurements(adjustment)` helper: check that `adjusted_bust_cm`, `adjusted_waist_cm`, `adjusted_hips_cm` are all non-NULL and >= 0; raise `ReportCreationError` naming the offending zone if not. _Req 2 AC3 · Design §Components and Interfaces_

- [x] 13. Implement `_assert_fabric_exists(fabric_id, db)` and `_assert_model_exists(model_id, db)` helpers following the same pattern as `_assert_user_exists`. _Req 4 AC1–2 · Design §Components and Interfaces_

- [x] 14. Implement `_build_snapshot(adjustment) -> dict` helper: return a dict with the seven fields of `AdjustedMeasurementsSnapshot` sourced from the ORM adjustment object. _Req 2 AC1; Req 1 AC4 · Design §Data Models_

- [x] 15. Implement `ReportService.create_report_from_event(event, db)`: execute the five guards in order (user → adjustment → measurements → fabric → model), build the snapshot dict, INSERT a new `RapportMesure` row (always INSERT, never UPSERT), commit, refresh, and return the ORM object. _Req 1 AC1, AC4–5; Req 2; Req 3 AC4; Req 4 AC1–3; Req 8 AC2 · Design §Components_

- [x] 16. Implement `ReportService.get_report(report_id, caller_cni, caller_role, db)`: load by PK (HTTP 404 if missing), enforce client ownership check (HTTP 403 if client CNI mismatch), allow tailor and admin roles unconditionally. _Req 5 AC1–5 · Design §Components and Interfaces_

- [x] 17. Implement `ReportService.list_reports_for_client(cni, db)`: query all `rapport_mesure` rows for the CNI ordered by `generated_at DESC`; return empty list if none exist. _Req 6 AC1–2 · Design §Components and Interfaces_

- [x] 18. Implement `ReportService.list_reports_for_client_as_tailor(target_cni, db)`: call `_assert_user_exists` first (HTTP 404 if missing), then delegate to `list_reports_for_client`. _Req 7 AC1–4 · Design §Components and Interfaces_

### Phase 4 — Event Handler

- [x] 19. Implement `make_compatibility_evaluated_handler(session_factory)` factory in `report_handler.py`: (1) parse raw payload with `CompatibilityEvaluatedEvent`, log ERROR + return on failure; (2) open `AsyncSession`, call `create_report_from_event()`, log ERROR + return on exception; (3) publish `ReportSavedEvent` to EventBus (fire-and-forget); (4) catch EventBus exceptions, log WARNING, do NOT re-raise. _Req 1 AC1–2; Req 4 AC4; Req 9 AC1–3 · Design §Components and Interfaces_

- [x] 20. Confirm that `make_compatibility_evaluated_handler` is imported and subscribed in `main.py lifespan` (validates task 3 is complete and wired correctly). _Design §Components and Interfaces / Registration in main.py_

### Phase 5 — HTTP Router

- [x] 21. Implement `GET /reports/{report_id}` in `report_router.py`: resolve `current_user` from Bearer JWT, call `ReportService.get_report()`, call `build_display_hints()`, return `ReportResponse` with HTTP 200. Note: register `/reports/me` route before `/reports/{report_id}` to prevent path parameter conflict. _Req 5 AC1–5 · Design §Components and Interfaces_

- [x] 22. Implement `GET /reports/me` in `report_router.py`: call `ReportService.list_reports_for_client(current_user.cni)`, build `ReportSummary` list (each item includes `verdict_color`), return `ReportListResponse` with HTTP 200. _Req 6 AC1–4 · Design §Components and Interfaces_

- [x] 23. Implement `GET /reports/client/{cni}` in `report_router.py`: check `current_user.role IN ("tailor", "admin")` → HTTP 403 if not; call `ReportService.list_reports_for_client_as_tailor(cni)`; return `ReportListResponse` with HTTP 200. _Req 7 AC1–5 · Design §Components and Interfaces_

### Phase 6 — Unit & Integration Tests

- [x] 24. Write unit tests for `build_display_hints()`: `"compatible"` → `verdict_color="green"`, `highlight_zones=[]`; `"minor_adjustments"` → `"orange"`, `[]`; `"incompatible"` with two zones → `"red"`, `["bust","waist"]`. _Req 3 AC1–3_

- [x] 25. Write unit tests for `_validate_measurements()`: all zones >= 0 → no exception; one zone negative → `ReportCreationError` with zone name in message; one zone NULL → `ReportCreationError`. _Req 2 AC3_

- [x] 26. Write unit tests for `CompatibilityEvaluatedEvent` Pydantic schema: valid compatible payload parses; valid incompatible payload with `incompatible_zones` populates the field; invalid `verdict` value raises `ValidationError`; CNI length != 9 raises `ValidationError`. _Req 3 AC5; Req 1 AC1_

- [x] 27. Write unit test for `ReportSavedEvent` schema: verify `type`, `cni`, `report_id` (str), and `date_generation` (str) field names and types match exactly the payload consumed by Module 1's `handle_report_saved`. _Req 9 AC2_

- [x] 28. Write integration tests for `GET /reports/{report_id}`: client retrieves own report → HTTP 200 with `display_hints`; client retrieves another client's report → HTTP 403; tailor retrieves any report → HTTP 200; non-existent `report_id` → HTTP 404; no JWT → HTTP 401. _Req 5 AC1–5_

- [x] 29. Write integration tests for `GET /reports/me`: client with 3 reports → HTTP 200, list of 3 ordered newest first; client with no reports → HTTP 200, `reports=[]`, `total=0`. _Req 6 AC1–2_

- [x] 30. Write integration tests for `GET /reports/client/{cni}`: tailor with valid CNI and reports → HTTP 200; tailor with valid CNI, no reports → HTTP 200 `total=0`; client call → HTTP 403; tailor with unknown CNI → HTTP 404. _Req 7 AC1–5_

- [x] 31. Write integration test for event handler happy path: emit valid `compatibility.evaluated` event (compatible verdict) → verify exactly one `rapport_mesure` row inserted with correct cni, verdict, and snapshot; verify `report.saved` published with correct payload structure. _Req 1 AC1–2; Req 9 AC1–2_

- [x] 32. Write integration tests for event handler error paths: missing `adjustment_id` → no DB row, ERROR logged; negative measurement in adjustment → no DB row, ERROR logged; missing `fabric_id` → no DB row, ERROR logged; EventBus publish raises exception → DB row still committed, WARNING logged, no re-raise. _Req 2 AC2–3; Req 4 AC1; Req 4 AC4_

- [x] 33. Write integration test for immutability: emit same `compatibility.evaluated` payload twice → verify two distinct `rapport_mesure` rows with different `id_report` and `generated_at` values (no upsert). _Req 8 AC2_

### Phase 7 — Property-Based Tests (Hypothesis)

- [x] 34. Write Hypothesis property test for `build_display_hints()`: (Property 1) for all valid verdicts, `verdict_color` is always one of `{"green","orange","red"}` and `highlight_zones` is always a list; (Property 2) `highlight_zones` is always `[]` when verdict is not `"incompatible"`; (Property 3) `len(highlight_zones) == len(incompatible_zones)` when verdict is `"incompatible"`. _Design §Correctness Properties 1–3; Req 3 AC1–3_

- [x] 35. Write Hypothesis property test for `AdjustedMeasurementsSnapshot` round-trip: for any valid snapshot dict, `AdjustedMeasurementsSnapshot(**d).model_dump()` round-trips without data loss. _Design §Correctness Property 4; Req 2 AC1_

- [x] 36. Write Hypothesis property test for `_validate_measurements()`: for any three values all >= 0 no exception is raised; for any set where at least one value is < 0 `ReportCreationError` is always raised. _Design §Correctness Property 5; Req 2 AC3_

- [x] 37. Write Hypothesis metamorphic property test for report list ordering invariant: for N reports with arbitrary `generated_at` timestamps for the same CNI, `list_reports_for_client()` always returns them in non-increasing `generated_at` order. _Design §Correctness Property 6; Req 6 AC1_

### Phase 8 — Documentation

- [x] 38. Update `backend/app/modules/business_rules/README.md`: add a Module 7 section covering the event-driven creation flow, the three API endpoints with their access rules, the `rapport_mesure` table ownership, and the `report.saved` event contract for Module 1. _Design §Inter-Module Data Contracts_

- [x] 39. Cross-check with Module 1 owner: confirm that `handle_report_saved` in `backend/app/modules/auth_user_profile/events/handlers.py` reads the fields `type`, `cni`, `report_id` (string), and `date_generation` (ISO string) exactly as `ReportSavedEvent` emits them. _Req 9 AC2 · Design §Inter-Module Data Contracts_

---

## Notes

- Module 7 files use the `report_` prefix to coexist with Module 5 files in the same `business_rules/` package without naming conflicts.
- Report creation is always INSERT — never upsert. A second event for the same combination of inputs produces a second distinct row (Req 8 AC2).
- The `report.saved` EventBus publish is fire-and-forget. A publish failure after a committed DB write logs a WARNING but never causes a rollback or exception propagation.
- `display_hints` is derived at read time and is NOT stored in the database — computed on every API response by `build_display_hints()`.
- Register `GET /reports/me` before `GET /reports/{report_id}` in FastAPI to prevent `"me"` being interpreted as a UUID path parameter.

---

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": [1] },
    { "wave": 2, "tasks": [2, 3, 4] },
    { "wave": 3, "tasks": [5, 6] },
    { "wave": 4, "tasks": [7] },
    { "wave": 5, "tasks": [8] },
    { "wave": 6, "tasks": [9, 10, 11, 12, 13, 14] },
    { "wave": 7, "tasks": [15, 16, 17, 18] },
    { "wave": 8, "tasks": [19, 20] },
    { "wave": 9, "tasks": [21, 22, 23] },
    { "wave": 10, "tasks": [24, 25, 26, 27, 28, 29, 30, 31, 32, 33] },
    { "wave": 11, "tasks": [34, 35, 36, 37] },
    { "wave": 12, "tasks": [38, 39] }
  ]
}
```
