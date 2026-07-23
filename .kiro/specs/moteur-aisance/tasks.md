# Tasks — Module 5: Ease Allowance Calculation Engine
# (Moteur de calcul d'aisance — Liste des tâches d'implémentation)

Each task references the Story (US-xx) and Acceptance Criterion (AC-xx.x) it implements,
plus the design section (§x.x) it corresponds to.
Tasks are ordered for sequential execution — later tasks depend on earlier ones.

---

## Phase 0 — Project Setup

- [ ] **T-00.1** Create the module directory structure under
  `backend/app/modules/business_rules/`:
  `__init__.py`, `router.py`, `service.py`, `engine.py`,
  `schemas.py`, `models.py`, `dependencies.py`.
  > _Design §2_

- [ ] **T-00.2** Register the `business_rules` router in `backend/main.py`
  at prefix `/api/v1/ease` with tag `ease-allowance`.
  > _Design §5_

---

## Phase 1 — Database Migration

- [ ] **T-01.1** Write and execute the SQL migration for the `ease_rules` reference table:
  columns `elasticity_category` (PK), `ease_delta_cm`, `description`;
  seed the three rows (`rigid` = +4.0, `semi-stretch` = +2.0, `stretch` = −2.0).
  > _AC-02.1, AC-02.2, AC-02.3, NFR-06 · Design §3.1_

- [ ] **T-01.2** Write and execute the SQL migration for the `measurement_adjustments` table:
  all columns including `DECIMAL(5,1)` adjusted values, `DECIMAL(4,1)` per-zone ease,
  `ease_source` CHECK constraint, `UNIQUE (session_id, fabric_id)` constraint,
  `updated_at` trigger (reuses `set_updated_at()` from Module 2),
  and RLS policies (SELECT / INSERT / UPDATE) scoped to session ownership.
  > _AC-01.6, AC-03.1, AC-03.2, NFR-03, NFR-04 · Design §3.2_

---

## Phase 2 — ORM Models & Schemas

- [ ] **T-02.1** Implement SQLAlchemy ORM model `EaseRule` in `models.py`
  mapping `ease_rules` (PK `elasticity_category`, `ease_delta_cm`, `description`).
  > _Design §3.1_

- [ ] **T-02.2** Implement SQLAlchemy ORM model `MeasurementAdjustment` in `models.py`
  mapping all columns of `measurement_adjustments`, including the
  `UniqueConstraint('session_id', 'fabric_id')` and the `ease_source` column.
  > _AC-01.6, AC-03.1, AC-03.2 · Design §3.2_

- [ ] **T-02.3** Implement all Pydantic schemas in `schemas.py`:
  `AdjustmentRequest`, `ZoneDetail`, `AdjustmentResponse`,
  `AdjustmentSummary`, `AdjustmentListResponse`.
  > _Design §4_

---

## Phase 3 — Ease Engine

- [ ] **T-03.1** Implement module-level constants and `_resolve_delta()` in `engine.py`:
  `_EASE_RULES` dict, `_DEFAULT_EASE_CM = 3.0`, `_FLOOR_CM = 0.0`, `_WARN_CM = 30.0`.
  > _AC-02.1, AC-02.2, AC-02.3, AC-02.4 · Design §6.2_

- [ ] **T-03.2** Implement `_compute_zone(raw, delta) → (adjusted_cm, warnings)` in `engine.py`:
  apply delta, clamp to `_FLOOR_CM`, append warning strings for floor-clamp (< 0 cm)
  and suspect-value (0 cm < adjusted < 30 cm) cases.
  > _AC-04.1, AC-04.2 · Design §6.3_

- [ ] **T-03.3** Implement `EaseInput`, `ZoneResult`, `EaseOutput` dataclasses in `engine.py`.
  > _Design §6.1_

- [ ] **T-03.4** Implement `EaseEngine.compute(inp: EaseInput) → EaseOutput` in `engine.py`:
  resolve delta → compute all three zones → collect warnings → add fallback warning
  when `ease_source == 'default_fallback'` → return `EaseOutput`.
  > _AC-02.1 – AC-02.4, AC-03.1, AC-04.1, AC-04.2 · Design §6.4_

- [ ] **T-03.5** AST syntax check on `engine.py`.

---

## Phase 4 — Service Layer

- [ ] **T-04.1** Implement `_load_session_or_raise(session_id, user_id, db)` helper in `service.py`:
  load `CaptureSession` by PK; raise HTTP 404 if missing, HTTP 403 if `user_id` mismatch.
  > _AC-01.2 · Design §7_

- [ ] **T-04.2** Implement `_load_raw_measurement_or_raise(session_id, db)` helper:
  query `raw_measurements` for the session; raise HTTP 424 with French message if absent.
  > _AC-01.3, AC-07.1 · Design §7_

- [ ] **T-04.3** Implement `_load_fabric_or_raise(fabric_id, db)` helper:
  join `fabrics` + `fabric_categories`, return `(fabric_name, elasticity_category)`;
  raise HTTP 404 if fabric not found.
  > _AC-01.4 · Design §8_

- [ ] **T-04.4** Implement `_upsert_adjustment(session_id, fabric_id, raw, output, db)`
  helper using SQLAlchemy's `insert(...).on_conflict_do_update(...)` on the
  `(session_id, fabric_id)` unique constraint. Returns `(adjustment, is_new: bool)`.
  > _AC-01.5, AC-01.6 · Design §8_

- [ ] **T-04.5** Implement `EaseCalculationService.compute_adjustment(user_id, session_id,
  fabric_id, db)` in `service.py`: wire all four helpers → call `EaseEngine.compute()` →
  emit `logger.warning()` for each entry in `output.warnings` → call `_upsert_adjustment`
  → return `(adjustment, is_new)`.
  > _US-01, US-02, US-03, US-04, AC-02.4, AC-04.1, AC-04.2 · Design §7_

- [ ] **T-04.6** Implement `EaseCalculationService.get_adjustment(adjustment_id, user_id, db)`:
  load by PK, assert ownership via session join, set `data_integrity_warning` flag
  if session status ≠ `success`, join fabric for name + category.
  > _AC-05.1, AC-05.2, AC-07.1 · Design §5.2_

- [ ] **T-04.7** Implement `EaseCalculationService.list_adjustments(session_id, user_id, db)`:
  assert session ownership, query all adjustments ordered by `calculated_at DESC`.
  > _AC-06.1, AC-06.2 · Design §5.3_

---

## Phase 5 — Auth & Dependency Injection

- [ ] **T-05.1** Implement `get_current_user` in `dependencies.py` for the `business_rules`
  module: decode Bearer JWT (reuse the same pattern as `measurements/dependencies.py`),
  return `user_id: UUID`, raise HTTP 401 on failure.
  > _AC-01.1, NFR-02_

- [ ] **T-05.2** Implement `get_db` async session dependency in `dependencies.py`,
  reusing `AsyncSessionFactory` from the shared engine setup.
  > _Design §2_

- [ ] **T-05.3** Implement `get_adjustment_or_404` dependency: load `MeasurementAdjustment`
  by PK, raise HTTP 404 if missing (ownership check deferred to service layer).
  > _AC-05.2 · Design §5.2_

---

## Phase 6 — API Router

- [ ] **T-06.1** Implement `POST /adjustments` endpoint in `router.py`:
  call `EaseCalculationService.compute_adjustment()`;
  return HTTP **201** for new records, HTTP **200** for overwrites (AC-01.6).
  > _US-01, AC-01.1 – AC-01.6 · Design §5.1_

- [ ] **T-06.2** Implement `GET /adjustments/{adjustment_id}` endpoint:
  call `EaseCalculationService.get_adjustment()`;
  return `AdjustmentResponse` with `data_integrity_warning` flag.
  > _AC-05.1, AC-05.2, AC-07.1 · Design §5.2_

- [ ] **T-06.3** Implement `GET /sessions/{session_id}/adjustments` endpoint:
  call `EaseCalculationService.list_adjustments()`;
  return `AdjustmentListResponse` (empty list when none exist).
  > _AC-06.1, AC-06.2 · Design §5.3_

---

## Phase 7 — Integration & Smoke Testing

- [ ] **T-07.1** Happy path smoke test (curl / Postman):
  - Complete a Module 2 session to `success` → call `POST /adjustments` with a
    `rigid` fabric → verify `adjusted_bust_cm = raw_bust_cm + 4.0`,
    `ease_source = "rule"`, HTTP 201.
  > _AC-01.5, AC-02.1_

- [ ] **T-07.2** Recompute / upsert test:
  - Call `POST /adjustments` again for the same `(session_id, fabric_id)` →
    verify HTTP 200 (not 201), same `adjustment_id` in response, `updated_at` changed.
  > _AC-01.6_

- [ ] **T-07.3** All three elasticity categories:
  - Repeat with `semi-stretch` fabric → verify delta = +2.0 cm.
  - Repeat with `stretch` fabric → verify delta = −2.0 cm.
  > _AC-02.2, AC-02.3_

- [ ] **T-07.4** Default fallback test:
  - Temporarily set a fabric's category to `null` (or an unknown string) in the DB →
    call `POST /adjustments` → verify `ease_source = "default_fallback"`,
    delta = +3.0 cm, HTTP 201/200 (not a 4xx), WARNING in server logs.
  > _AC-02.4_

- [ ] **T-07.5** 424 guard test:
  - Call `POST /adjustments` with a `session_id` that is in `processing` status →
    verify HTTP 424 with French message.
  > _AC-01.3_

- [ ] **T-07.6** Multi-fabric comparison test:
  - Compute adjustments for the same session with two different fabrics →
    call `GET /sessions/{session_id}/adjustments` → verify both appear in the list,
    newest first, each with correct adjusted values.
  > _AC-06.1, US-06_

- [ ] **T-07.7** Cross-user isolation:
  - Attempt `GET /adjustments/{adjustment_id}` with User B's token for User A's
    adjustment → verify HTTP 403.
  > _AC-05.2, NFR-03_

---

## Phase 8 — Documentation

- [ ] **T-08.1** Write `backend/app/modules/business_rules/README.md`:
  module purpose, endpoint table, `ease_rules` seeded values,
  environment variables, inter-module DB contracts for M7.
  > _Design §10_

- [ ] **T-08.2** Confirm Module 7 owner has access to the canonical SQL query in
  `design.md §10` and understands the `measurement_adjustments` table ownership rule.
