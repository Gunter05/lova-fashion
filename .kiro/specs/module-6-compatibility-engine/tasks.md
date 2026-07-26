# Implementation Plan: Module 6 — Fabric/Model/Silhouette Compatibility Engine

## Overview

Implement Module 6 alongside the existing Module 5 code inside
`backend/app/modules/business_rules/`. The work breaks into eight sequential groups:
database migration → ORM models → Pydantic schemas → pure `RuleEvaluator` engine →
`CompatibilityService` orchestrator → router/endpoints → unit tests → property-based
tests → integration tests. Every file that already contains Module 5 code is **extended,
never overwritten**.

---

## Tasks

- [x] 1. Create the database migration for Module 6 tables
  - [x] 1.1 Write `backend/migrations/007_create_compatibility_tables.sql`
    - Create `compatibility_rules` table with columns `rule_id`, `cut_type`,
      `fabric_property`, `zone_id` (FK → `critical_zone.zone_id`, nullable),
      `mathematical_condition` (VARCHAR 200), `severity_level` CHECK IN
      ('Incompatible','Reserve'), `explanation_message` (TEXT, ≤ 500 chars CHECK),
      `is_active` BOOLEAN DEFAULT TRUE, `version` INTEGER DEFAULT 1, `admin_id` UUID,
      `created_at`, `updated_at` TIMESTAMPTZ
    - Create compound index `idx_rules_cut_fabric_active` on
      `(cut_type, fabric_property, is_active)`
    - Create `model_morphology` table with composite PK `(model_id, morphology_id)`,
      `suitability_score` CHECK IN ('Ideal','Flattering','Avoid'), FK to `model.model_id`
    - Create `verdict_evaluations` table with all non-nullable FK columns
      (`client_id`, `model_id`, `fabric_id`, `measurements_id`, `morphology_id`),
      `global_status` CHECK constraint, `missing_data_log` TEXT nullable,
      `fabric_recommendation` VARCHAR(50) nullable; add index
      `idx_verdict_client` on `(client_id, created_at DESC)`
    - Create `risk_zones` table with FK `evaluation_id` ON DELETE CASCADE, nullable
      `rule_id` and `zone_id`, `calculated_variance` NUMERIC(8,4), `localized_verdict`
      CHECK IN ('Incompatible','Reserve'), `explanation` TEXT NOT NULL, `rule_version` INT
    - Add `updated_at` auto-trigger for `compatibility_rules`
    - Enable RLS on `verdict_evaluations` and `risk_zones` with owner-select policies
    - _Requirements: 2.1, 7.1–7.7, 9.1, 13.3_

- [x] 2. Add Module 6 ORM models to `models.py`
  - [x] 2.1 Add `CompatibilityRule` SQLAlchemy model
    - Append `CompatibilityRule` class to `backend/app/modules/business_rules/models.py`
      inheriting from the existing `Base`; do not touch `EaseRule` or
      `MeasurementAdjustment`
    - Add `UniqueConstraint("cut_type","fabric_property","zone_id","is_active",
      name="uq_rule_cut_fabric_zone_active")`, severity CHECK, condition-length CHECK,
      explanation-length CHECK
    - All columns match the design spec: `rule_id`, `cut_type`, `fabric_property`,
      `zone_id` (nullable UUID FK), `mathematical_condition`, `severity_level`,
      `explanation_message`, `is_active`, `version`, `admin_id`, `created_at`,
      `updated_at`
    - _Requirements: 2.1, 2.2, 9.1–9.3, 13.3_

  - [x] 2.2 Add `ModelMorphology`, `VerdictEvaluation`, and `RiskZone` ORM models
    - Append `ModelMorphology` association table (composite PK, `suitability_score`
      CHECK) to the same file
    - Append `VerdictEvaluation` with `global_status` CHECK, all FK columns,
      `missing_data_log`, `fabric_recommendation`, and `selectin` relationship to
      `RiskZone`
    - Append `RiskZone` with `localized_verdict` CHECK, nullable `rule_id` / `zone_id`,
      `calculated_variance` NUMERIC, `rule_version`, and back-populates relationship
    - _Requirements: 4.1–4.5, 5.1–5.6, 7.1–7.7, 12.1–12.4, 13.3_


- [x] 3. Add Module 6 Pydantic schemas to `schemas.py`
  - [x] 3.1 Add request schemas
    - Append `VerificationRequest` (fields: `adjustment_id`, `model_id`, `fabric_id`,
      `morphology_id`, `client_id` — all UUID) to
      `backend/app/modules/business_rules/schemas.py`; do not touch Module 5 schemas
    - Append `CompatibilityRuleCreate` with `cut_type`, `fabric_property`,
      `zone_id: UUID | None`, `mathematical_condition: str = Field(..., max_length=200)`,
      `severity_level: Literal["Incompatible","Reserve"]`,
      `explanation_message: str | None = Field(None, max_length=500)`, `is_active: bool`
    - Append `CompatibilityRuleUpdate` (all fields optional) with immutability note in
      docstring; `cut_type`, `fabric_property`, `zone_id` must NOT be present — raise
      422 in service if caller attempts to send them
    - _Requirements: 1.1–1.2, 9.1–9.2, 10.1, 13.4_

  - [x] 3.2 Add response schemas
    - Append `RiskZoneResponse` with all fields from the `RiskZone` ORM model plus
      `model_config = {"from_attributes": True}`
    - Append `VerdictEvaluationResponse` with `evaluation_id`, `global_status` (Literal
      of 5 values), `created_at`, `fabric_recommendation: str | None`, `risk_zones:
      list[RiskZoneResponse]`, `model_config = {"from_attributes": True}`
    - Append `CompatibilityRuleResponse` with all rule fields and
      `model_config = {"from_attributes": True}`
    - _Requirements: 6.1–6.4, 10.2, 10.4, 13.4_


- [x] 4. Implement `RuleEvaluator` in `engine.py`
  - [x] 4.1 Add `RuleRecord`, `RuleInput`, `RiskZoneDict` dataclasses
    - Append dataclasses to `backend/app/modules/business_rules/engine.py` below the
      existing Module 5 dataclasses; do not modify `EaseEngine`, `EaseInput`,
      `ZoneResult`, `EaseOutput`, or any private helpers
    - `RuleRecord`: `rule_id: uuid.UUID`, `zone_id: uuid.UUID | None`,
      `zone_name: str`, `mathematical_condition: str`, `severity_level: str`,
      `explanation_message: str | None`, `version: int`
    - `RuleInput`: `rules: list[RuleRecord]`, `zone_measurements: dict[str, float]`,
      `critical_zone_ids: list[uuid.UUID]`
    - `RiskZoneDict`: `rule_id: uuid.UUID | None`, `zone_id: uuid.UUID | None`,
      `calculated_variance: float`, `localized_verdict: str`, `explanation: str`,
      `rule_version: int`, `warnings: list[str]`
    - _Requirements: 8.1, 13.3_

  - [x] 4.2 Implement `_safe_eval_condition` helper and `RuleEvaluator` class
    - Add private `_safe_eval_condition(condition: str, value: float) -> bool` using
      `simpleeval.SimpleEval`; bind only `{"value": value}` with no operator extensions;
      raise `ValueError` on `NameNotDefined` or any parse error
    - Add `RuleEvaluator` class with a single `evaluate(self, inp: RuleInput) ->
      list[RiskZoneDict]` method implementing the pseudocode algorithm from the design:
      iterate rules, map `zone_name` → measurement, call `_safe_eval_condition`, catch
      `ValueError` (skip rule, append warning), on fire build `RiskZoneDict` with
      fallback explanation when `explanation_message` is null/empty
    - Add `_build_default_explanation(zone_name, rule_id) -> str` private helper
    - Ensure `evaluate()` never raises; always returns a list (empty or not)
    - _Requirements: 2.2, 3.1–3.9, 6.3, 8.1–8.5_


- [x] 5. Implement `CompatibilityService` in `service.py`
  - [x] 5.1 Add private data-loading helpers
    - Append all helpers to `backend/app/modules/business_rules/service.py` below the
      existing `EaseCalculationService`; do not modify any Module 5 functions
    - `_load_adjustment_or_422(adjustment_id, db)` — load `MeasurementAdjustment` by PK,
      raise HTTP 422 if not found; validate bust/waist/hips adjusted_cm > 0 and ≤ 300,
      raise HTTP 422 with field name and value if violated
    - `_load_model_or_422(model_id, db)` — load Model, raise HTTP 422 if status ≠
      `Published` (include current status in error)
    - `_load_fabric_or_422(fabric_id, db)` — join Fabric + FabricCategory, raise HTTP 422
      if `fabric_status ≠ available` (include current status in error)
    - `_load_morphology_or_422(morphology_id, db)` — load BodyShape by PK, raise HTTP 422
      if not found
    - `_load_active_rules(cut_type, fabric_property, db)` — execute the version-deduped
      SQL from the design (MAX version per zone_id group), return
      `list[RuleRecord]`; on DB error set `global_status="Failed"` and raise HTTP 500
    - _Requirements: 1.1–1.12, 2.1–2.7, 13.1–13.2_

  - [x] 5.2 Add morphology-check, fabric-link-check, and verdict-aggregation helpers
    - `_check_morphology_link(model_id, morphology_id, db) -> str | None` — query
      `model_morphology`, return `suitability_score` or `None`; on DB error raise HTTP 500
      with `global_status="Failed"`
    - `_check_fabric_link(model_id, fabric_id, db) -> str | None` — query
      `MODEL_FABRIC_LINK` / `model_fabric` table, return `recommendation_level` or
      `None`; if `None` generate a `Reserve` `RiskZoneDict` with `rule_id=None`,
      `zone_id=None`, and the standard explanation from Req 12.3
    - `_aggregate_verdict(risk_zones: list[RiskZoneDict]) -> str` — pure function:
      returns `"Incompatible"` if any `localized_verdict=="Incompatible"`, else
      `"Compatible_with_Reservations"` if any `=="Reserve"`, else `"Compatible"`
    - `_persist_evaluation(eval_data, risk_zones, db)` — single `async with db.begin()`
      transaction; INSERT `VerdictEvaluation`, flush for PK, batch-INSERT all `RiskZone`
      rows; UUID collision retry once; on any failure roll back and raise HTTP 500
    - _Requirements: 4.1–4.5, 5.1–5.6, 7.1–7.8, 12.1–12.4_

  - [x] 5.3 Implement `CompatibilityService.verify()` orchestration method
    - Implement the 6-phase pipeline as a `@staticmethod async def verify(request,
      user_id, db) -> VerdictEvaluationResponse`:
      Phase 1 — call all four `_load_*_or_422` helpers in sequence
      Phase 2 — call `_load_active_rules`; if empty → build Indeterminate
      `VerdictEvaluation`, persist, emit `logger.error` with structured fields, return 201
      Phase 3 — instantiate `RuleEvaluator().evaluate(RuleInput(...))` (pure, no DB)
      Phase 4 — call `_check_morphology_link`; if `suitability_score=="Avoid"` append
      morphology `RiskZoneDict` (severity from admin config or default `"Reserve"`)
      Phase 5 — call `_check_fabric_link`; append Reserve `RiskZoneDict` if no link found
      Phase 6 — call `_aggregate_verdict`; verify Incompatible invariant (Req 5.3);
      call `_persist_evaluation`; return `VerdictEvaluationResponse`
    - _Requirements: 1.12, 2.3–2.7, 3.1–3.9, 4.1–4.5, 5.1–5.6, 6.1–6.4, 7.1–7.8,
      11.1–11.4, 12.1–12.4_

  - [x] 5.4 Implement `CompatibilityService` rule administration methods
    - `create_rule(body, admin_id, db)` — INSERT `CompatibilityRule` with `version=1`
      and the requesting admin's UUID; catch `IntegrityError` on unique constraint and
      raise HTTP 409
    - `update_rule(rule_id, body, db)` — load rule or raise HTTP 404; increment `version`
      by 1; apply only mutable fields (`mathematical_condition`, `severity_level`,
      `explanation_message`, `is_active`); return updated rule
    - `list_rules(db, limit=200)` — SELECT all rules with LIMIT 200, return list
    - `get_evaluation(evaluation_id, db)` — load `VerdictEvaluation` with
      `selectin`-loaded `risk_zones` or raise HTTP 404
    - _Requirements: 9.1–9.7, 10.4–10.5_

- [x] 6. Checkpoint — wire `simpleeval` dependency
  - Add `simpleeval==0.9.13` to `backend/requirements.txt` if not already present
  - Verify `from simpleeval import SimpleEval` imports cleanly in the Python environment
  - _Requirements: 8.4 (design dependency table)_


- [x] 7. Add `require_admin` dependency and extend `dependencies.py`
  - [x] 7.1 Implement `require_admin` dependency
    - Append `require_admin` async function to
      `backend/app/modules/business_rules/dependencies.py`; do not modify
      `get_db`, `get_current_user`, or `get_adjustment_or_404`
    - Decode JWT, read `is_admin` claim; raise HTTP 403 if claim is absent or `false`;
      return `user_id: uuid.UUID` on success
    - Response body on 403 must NOT contain any rule content
      (`rule_id`, `mathematical_condition`, `severity_level`, `explanation_message`)
    - _Requirements: 9.5, 13.1_

- [x] 8. Add Module 6 router section and mount in `main.py`
  - [x] 8.1 Create the compatibility `APIRouter` section in `router.py`
    - Append a new `compatibility_router = APIRouter()` block to
      `backend/app/modules/business_rules/router.py`; keep the existing `router`
      (Module 5) untouched
    - `POST /verifications` — calls `CompatibilityService.verify()`, returns HTTP 201;
      requires `get_current_user`
    - `GET /verifications/{evaluation_id}` — calls `CompatibilityService.get_evaluation()`
      returns 200 or 404; requires `get_current_user`
    - `POST /compatibility-rules` — calls `CompatibilityService.create_rule()`, returns
      201; requires `require_admin`
    - `PATCH /compatibility-rules/{rule_id}` — calls `CompatibilityService.update_rule()`,
      returns 200; requires `require_admin`; rejects immutable field changes with 422
    - `GET /compatibility-rules` — calls `CompatibilityService.list_rules()`, returns 200;
      requires `require_admin`
    - _Requirements: 9.1–9.7, 10.1–10.6, 13.1, 13.6_

  - [x] 8.2 Mount `compatibility_router` in `main.py`
    - Import `compatibility_router` from `app.modules.business_rules.router` in
      `backend/main.py`
    - Add `app.include_router(compatibility_router, prefix="/api/v1/compatibility",
      tags=["compatibility"])` without disturbing existing router registrations
    - _Requirements: 10.1, 13.5_


<<<<<<< HEAD
- [-] 9. Checkpoint — Ensure all existing Module 5 tests still pass
=======
- [ ] 9. Checkpoint — Ensure all existing Module 5 tests still pass
>>>>>>> c901c5e7ca3365f37682d033a34f142ee4cb70be
  - Run `pytest backend/app/modules/business_rules/tests/test_engine.py
    backend/app/modules/business_rules/tests/test_service.py -x` and verify zero
    regressions before proceeding to Module 6 tests

- [x] 10. Extend `conftest.py` with Module 6 fixtures
  - [x] 10.1 Add Module 6 seed helpers and ORM schema registration to `conftest.py`
    - In `backend/app/modules/business_rules/tests/conftest.py`, add
      `BRBase.metadata.create_all` call for the new ORM models (`CompatibilityRule`,
      `ModelMorphology`, `VerdictEvaluation`, `RiskZone`) to the existing `engine`
      session-scoped fixture — they share the same `Base`; no separate fixture needed
    - Add `seed_compatibility_rule(db, cut_type, fabric_property, zone_name,
      condition, severity, explanation, admin_id) -> CompatibilityRule` helper
    - Add `seed_model(db, cut_type="Fitted", status="Published") -> Model` helper
      that inserts a minimal `Model` row and one `CriticalZone` row (bust/waist/hips)
    - Add `seed_model_morphology(db, model_id, morphology_id, score) -> None` helper
    - Add `seed_model_fabric_link(db, model_id, fabric_id, level) -> None` helper
    - Add `seed_verdict_evaluation(db, ...) -> VerdictEvaluation` helper for read
      endpoint integration tests
    - _Requirements: 8.5, 13.1_


- [x] 11. Write `RuleEvaluator` unit and property-based tests in `test_engine.py`
  - [x] 11.1 Add deterministQic unit tests for `RuleEvaluator`
    - Append Module 6 test functions to
      `backend/app/modules/business_rules/tests/test_engine.py`; do not modify or
      remove existing Module 5 tests
    - Implement test cases RE-01 through RE-10 exactly as specified in the design's
      Testing Strategy table:
      RE-01 empty rules → `[]`; RE-02 single matching rule → 1 item; RE-03 rule does not
      fire → `[]`; RE-04 two rules fire for different zones → 2 items; RE-05/RE-06
      severity propagated correctly to `localized_verdict`; RE-07 null explanation
      triggers fallback string; RE-08 malformed condition skipped, warning appended,
      no exception; RE-09 unknown zone_name skipped, warning appended; RE-10
      `rule_version` copied to output
    - _Requirements: 3.1–3.9, 6.3, 8.1–8.5_

  - [ ]* 11.2 Write property-based tests for `RuleEvaluator` (Property 1)
    - **Property 1: Determinism** — same inputs → identical `RiskZoneDict` lists
    - Implement `test_p1_determinism` using Hypothesis `@given(zone_measurements,
      severity)` strategy; call `evaluate()` twice, assert `result_1 == result_2`
    - **Validates: Requirements 3.9, 8.3**

  - [ ]* 11.3 Write property-based tests for `RuleEvaluator` (Property 2)
    - **Property 2: Verdict closure** — all `localized_verdict` values ∈
      `{"Incompatible", "Reserve"}`
    - Implement `test_p2_verdict_values_constrained` using `@given(zone_measurements)`
    - **Validates: Requirements 3.4, 3.5**

  - [ ]* 11.4 Write property-based tests for `RuleEvaluator` (Property 3)
    - **Property 3: Empty rules → empty output** — for any `zone_measurements`, an empty
      `rules` list always returns `[]`
    - Implement `test_p3_empty_rules_returns_empty` using `@given(zone_measurements)`
    - **Validates: Requirement 8.1**

  - [ ]* 11.5 Write property-based tests for `RuleEvaluator` (Property 4)
    - **Property 4: Explanation completeness** — every `RiskZoneDict` in the result has
      `len(rz.explanation.strip()) > 0`
    - Implement `test_p4_explanation_never_empty_on_fired_rule` with a rule whose
      `explanation_message=None` and condition always fires (`value >= 0.0`)
    - **Validates: Requirement 6.3**

  - [ ]* 11.6 Write property-based tests for `RuleEvaluator` (Property 8)
    - **Property 8: Malformed condition safety** — arbitrary `condition` strings of
      length 1–200 never cause an unhandled exception from `evaluate()`
    - Implement `test_p5_malformed_condition_never_raises` using
      `@given(zone_measurements, condition=st.text(min_size=1, max_size=200))`
    - **Validates: Requirement 8.4**


<<<<<<< HEAD
- [x] 12. Write `CompatibilityService` integration tests in `test_service.py`
  - [x] 12.1 Add happy-path and verdict-variant integration tests
=======
- [ ] 12. Write `CompatibilityService` integration tests in `test_service.py`
  - [ ] 12.1 Add happy-path and verdict-variant integration tests
>>>>>>> c901c5e7ca3365f37682d033a34f142ee4cb70be
    - Append Module 6 integration tests to
      `backend/app/modules/business_rules/tests/test_service.py`; do not modify
      existing Module 5 tests
    - Test `CompatibilityService.verify()` against the in-memory SQLite session
      (reuse the `db_session` fixture from `conftest.py`)
    - Cover: Compatible (no rules fire), Compatible_with_Reservations (Reserve rule
      fires), Incompatible (Incompatible rule fires), Indeterminate (no active rules),
      fabric link absent → Reserve RiskZone added, morphology `Avoid` → Reserve
      RiskZone added
    - Verify `VerdictEvaluation` and `RiskZone` rows are both present in DB after
      successful evaluation
    - _Requirements: 3.1–3.7, 4.1–4.4, 5.1–5.6, 7.1–7.3, 11.1–11.4, 12.1–12.4_

  - [ ]* 12.2 Write integration test for single-transaction rollback (Property 6)
    - **Property 6: No partial persistence** — if the `INSERT risk_zones` fails
      mid-transaction, the parent `VerdictEvaluation` row is also rolled back
    - Mock `db.flush()` to raise `IntegrityError` after the first flush; assert the
      `verdict_evaluations` table is empty after the error
    - **Validates: Requirement 7.7**

  - [ ]* 12.3 Write integration test for rule immutability (Property 7)
    - **Property 7: Immutability of past evaluations** — updating a
      `CompatibilityRule` does NOT modify an already-persisted `VerdictEvaluation`
      or its `RiskZone` rows; `rule_version` in `RiskZone` reflects the version at
      evaluation time
    - Persist an evaluation with a rule at version 1, then call
      `CompatibilityService.update_rule()` to increment version to 2; reload the
      original `RiskZone` and assert `rule_version == 1`
    - **Validates: Requirements 7.4, 7.2, 2.6**

  - [ ]* 12.4 Write integration tests for admin-API CRUD on `CompatibilityRule`
    - Test `create_rule()` returns HTTP 201 with new `rule_id` and `version=1`
    - Test duplicate `(cut_type, fabric_property, zone_id)` active rule raises HTTP 409
    - Test `update_rule()` increments `version` and rejects immutable field changes
      with HTTP 422
    - Test `list_rules()` respects the 200-row limit
    - Test non-admin `require_admin` raises HTTP 403 and leaks no rule content
    - _Requirements: 9.1–9.7_

<<<<<<< HEAD
- [~] 13. Checkpoint — Ensure all Module 5 and Module 6 tests pass
=======
- [ ] 13. Checkpoint — Ensure all Module 5 and Module 6 tests pass
>>>>>>> c901c5e7ca3365f37682d033a34f142ee4cb70be
  - Run `pytest backend/app/modules/business_rules/tests/ -x` and confirm zero failures
    before marking the implementation complete; ask the user if any questions arise


---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP; the 5
  property-based tests and 3 integration-test tasks are all optional sub-tasks.
- Files touched by Module 5 (`engine.py`, `models.py`, `schemas.py`, `service.py`,
  `router.py`, `dependencies.py`, `tests/conftest.py`, `tests/test_engine.py`,
  `tests/test_service.py`) are **extended only** — never rewritten. Each task is scoped
  to append-only changes that leave existing Module 5 symbols intact.
- New file created: `backend/migrations/007_create_compatibility_tables.sql`.
- `simpleeval==0.9.13` must be added to `backend/requirements.txt` before task 4.2.
- All `async def` handlers and service methods follow the project's FastAPI + SQLAlchemy
  async patterns (Req 13.1–13.6).
- Property tests are numbered to match the design's Correctness Properties section
  (Properties 1–8); not all properties have dedicated Hypothesis tests — Properties 4–7
  are covered by integration tests 12.1–12.3.

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "3.1"] },
    { "id": 3, "tasks": ["3.2", "4.1", "7.1"] },
    { "id": 4, "tasks": ["4.2"] },
    { "id": 5, "tasks": ["5.1", "8.1"] },
    { "id": 6, "tasks": ["5.2"] },
    { "id": 7, "tasks": ["5.3", "5.4"] },
    { "id": 8, "tasks": ["8.2", "10.1"] },
    { "id": 9, "tasks": ["11.1"] },
    { "id": 10, "tasks": ["11.2", "11.3", "11.4", "11.5", "11.6", "12.1"] },
    { "id": 11, "tasks": ["12.2", "12.3", "12.4"] }
  ]
}
```
