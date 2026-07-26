# Requirements Document

## Introduction

Module 6 is the **Compatibility Verification Engine** of the Lova Fashion application
(AWS re:Deploy 2026 — Fashion Theme). It determines whether a specific combination of
adjusted body measurements, garment model constraints, and fabric properties is
manufacturable and wearable.

Given inputs from three upstream modules — Module 5 (adjusted measurements with ease
applied), Module 4 (garment model constraints and critical zones), and Module 3 (fabric
properties) — the engine evaluates each critical zone against a set of administrator-
configurable rules and produces exactly one of four verdicts:

- **Compatible** — all zones pass all active rules.
- **Compatible with Reservations** — minor deviations are tolerated, accompanied by
  per-zone warnings.
- **Incompatible** — at least one zone violates a hard threshold.
- **Indeterminate** — no rule exists for the encountered cut/fabric combination; the
  engine cannot render a verdict.

Every non-Compatible verdict includes structured per-zone explanations: the affected zone,
the violated rule, the severity level, an explanation text, and a recommendation.

All evaluations are persisted for audit purposes. The engine does not modify upstream data
and never retroactively alters previously generated evaluations when rules are updated.

The module lives in `backend/app/modules/business_rules/` alongside Modules 5 and 7, and
follows the project's async FastAPI + SQLAlchemy ORM + Supabase PostgreSQL patterns.

---

## Glossary

- **Verification_Engine**: The Module 6 service component that orchestrates compatibility
  evaluation; referenced as the subject of requirements in this document.
- **Compatibility_Rule**: A database-stored row in `compatibility_rules` that encodes a
  cut/fabric condition, a mathematical threshold expression, a severity level
  (`Incompatible` or `Reserve`), and an explanation message.
- **Verdict_Evaluation**: The persisted record of one compatibility check, keyed by
  `evaluation_id`.
- **Risk_Zone**: A persisted record within a Verdict_Evaluation that describes a single
  zone violation — the affected zone, the applied rule, the computed variance, and the
  localized verdict.
- **Critical_Zone**: A reference-data entity from Module 4 (`critical_zone` table)
  representing a body measurement zone constrained by a garment model (e.g. bust, waist,
  hips).
- **Adjusted_Measurements**: The output of Module 5 (`AdjustmentResponse`) containing
  ease-adjusted values for bust, waist, and hips in centimetres.
- **Model**: A garment pattern entity from Module 4 with `cut_type` (Fitted / Semi-fitted
  / Loose), `garment_type`, `status`, associated Critical_Zones, and associated fabrics.
- **Fabric**: A textile reference from Module 3 with `fabric_elasticity_rate` (0–100),
  `fabric_status` (`available` / `unavailable` / `archived`), and a parent
  `FabricCategory` with `reference_rigidity_level` (`rigid` / `semi-stretch` / `stretch`).
- **Morphology**: A body shape classification from the measurements module; associated to
  Models via `MODEL_MORPHOLOGY_LINK` with a `suitability_score` (`Ideal` / `Flattering` /
  `Avoid`).
- **MODEL_FABRIC_LINK**: Association table linking a Model to compatible Fabrics with a
  `recommendation_level` (`Highly Recommended` / `Accepted`).
- **MODEL_MORPHOLOGY_LINK**: Association table linking a Model to a Morphology with a
  `suitability_score`.
- **Global_Status**: The aggregate verdict of a Verdict_Evaluation: `Compatible`,
  `Compatible_with_Reservations`, `Incompatible`, `Indeterminate`, or `Failed`.
- **Calculated_Variance**: The numeric gap computed by the engine when evaluating a
  mathematical condition in a Compatibility_Rule against the adjusted measurements.
- **Severity_Level**: The classification of a rule violation: `Incompatible` (hard block)
  or `Reserve` (soft warning).
- **Admin**: A user with administrator rights who creates and updates Compatibility_Rules
  via the admin API.
- **Rule_Evaluator**: The pure, stateless sub-component of the Verification_Engine that
  applies Compatibility_Rules to measurements and produces per-zone verdicts.
- **Indeterminate**: A special Global_Status returned when no active Compatibility_Rule
  covers the cut/fabric combination of the request; distinct from `Incompatible`.

---

## Requirements

### Requirement 1: Input Validation and Completeness Check

**User Story:** As an end user, I want the engine to verify that all required data is
present before starting a compatibility check, so that I never receive a misleading or
partial verdict caused by missing upstream data.

#### Acceptance Criteria

1. WHEN a verification request is received, THE Verification_Engine SHALL verify that
   `adjustment_id`, `model_id`, `fabric_id`, and `morphology_id` are all present in the
   request body before executing any rule evaluation.

2. IF any of `adjustment_id`, `model_id`, `fabric_id`, or `morphology_id` is absent from
   the verification request, THEN THE Verification_Engine SHALL reject the request with
   HTTP 422 and return a structured error response listing each missing field by name.

3. WHEN a verification request is received with a valid `adjustment_id`, THE
   Verification_Engine SHALL retrieve the corresponding `AdjustmentResponse` from the
   `measurement_adjustments` table and confirm that `bust.adjusted_cm`,
   `waist.adjusted_cm`, and `hips.adjusted_cm` are all non-null, strictly greater than
   0.00 cm, and at most 300.00 cm.

4. IF any adjusted measurement zone value (`bust.adjusted_cm`, `waist.adjusted_cm`,
   `hips.adjusted_cm`) is zero, negative, or exceeds 300.00 cm, THEN THE
   Verification_Engine SHALL reject the verification with HTTP 422 and return a validation
   error identifying the aberrant zone, its value, and the violated bound.

5. WHEN a verification request is received with a valid `model_id`, THE
   Verification_Engine SHALL retrieve the corresponding Model and confirm that its
   `status` is `Published`.

6. IF the retrieved Model has a `status` other than `Published`, THEN THE
   Verification_Engine SHALL reject the verification with HTTP 422 and return an error
   response that includes the model's current status value.

7. WHEN a verification request is received with a valid `fabric_id`, THE
   Verification_Engine SHALL retrieve the corresponding Fabric and confirm that its
   `fabric_status` is `available`.

8. IF the retrieved Fabric has a `fabric_status` other than `available`, THEN THE
   Verification_Engine SHALL reject the verification with HTTP 422 and return an error
   response that includes the fabric's current status value.

9. WHEN a verification request is received with a valid `morphology_id`, THE
   Verification_Engine SHALL confirm that a Morphology record with that identifier exists
   in the system.

10. IF no Morphology record exists for the provided `morphology_id`, THEN THE
    Verification_Engine SHALL reject the verification with HTTP 422 and return an error
    response identifying the missing morphology record.

11. IF any upstream module (Module 3, 4, or 5) is unreachable during data retrieval, THEN
    THE Verification_Engine SHALL return HTTP 503 after at most two retry attempts and
    SHALL NOT persist a Verdict_Evaluation record for the failed request.

12. WHEN all validation checks in criteria 1–10 pass, THE Verification_Engine SHALL
    transition to the rule-loading phase without any additional operator action.

---

### Requirement 2: Configurable Rule Loading

**User Story:** As a catalog manager (admin), I want all compatibility thresholds to be
stored in the database so that I can adjust them without changing any application code,
and have those adjustments take effect immediately for future evaluations.

#### Acceptance Criteria

1. WHEN the Verification_Engine initiates an evaluation, THE Verification_Engine SHALL
   load all active Compatibility_Rules (where `is_active = true`) whose `cut_type` exactly
   matches the requested Model's `cut_type` and whose `fabric_property` exactly matches
   the Fabric's `reference_rigidity_level`.

2. THE Verification_Engine SHALL NOT contain any hard-coded numeric threshold values;
   all thresholds SHALL be sourced exclusively from the `compatibility_rules` table.

3. WHEN no active Compatibility_Rule exists for the combination of the Model's `cut_type`
   and the Fabric's `reference_rigidity_level`, THE Verification_Engine SHALL set the
   Global_Status to `Indeterminate` and SHALL NOT proceed to zone evaluation.

4. WHEN the Global_Status is set to `Indeterminate`, THE Verification_Engine SHALL record
   the unmatched `cut_type` and `fabric_property` combination in the `missing_data_log`
   field of the persisted Verdict_Evaluation, producing a testable observable artifact.

5. WHERE multiple active Compatibility_Rule rows exist for the same `cut_type` and
   `fabric_property`, THE Verification_Engine SHALL apply only the rows with the highest
   `version` number.

6. WHEN an Admin updates a Compatibility_Rule (changes threshold, severity, or
   explanation), THE Verification_Engine SHALL apply the updated rule exclusively to
   evaluations initiated after the update; previously persisted Verdict_Evaluations SHALL
   remain unchanged.

7. IF the database query to load Compatibility_Rules fails with a technical error, THEN
   THE Verification_Engine SHALL set Global_Status to `Failed`, persist the
   Verdict_Evaluation with the error cause in `missing_data_log`, and return HTTP 500 to
   the caller.

---

### Requirement 3: Zone-Level Rule Evaluation

**User Story:** As an end user, I want the engine to evaluate each critical body zone
independently, so that I receive a precise explanation for every zone that presents a
compatibility issue rather than a single global flag.

#### Acceptance Criteria

1. WHEN Compatibility_Rules are loaded and all inputs are valid, THE Rule_Evaluator SHALL
   evaluate each Critical_Zone associated with the requested Model independently, such that
   the evaluation inputs and outcome of one zone SHALL NOT influence the evaluation inputs
   of any other zone.

2. WHEN evaluating a Critical_Zone, THE Rule_Evaluator SHALL compute the
   Calculated_Variance by applying the Compatibility_Rule's `mathematical_condition`
   expression to the `adjusted_cm` value for that zone, where zone names `bust`, `waist`,
   and `hips` map to `bust.adjusted_cm`, `waist.adjusted_cm`, and `hips.adjusted_cm`
   respectively from the `AdjustmentResponse`.

3. WHEN a Compatibility_Rule fires for a given zone and multiple active rules match the
   same zone, THE Rule_Evaluator SHALL produce one Risk_Zone record per satisfied rule,
   not one per zone.

4. WHEN the computed Calculated_Variance satisfies a Compatibility_Rule's
   `mathematical_condition` and that rule's `severity_level` is `Incompatible`, THE
   Rule_Evaluator SHALL record a Risk_Zone with `localized_verdict = "Incompatible"` and
   SHALL attach the rule's `explanation_message` to the Risk_Zone.

5. WHEN the computed Calculated_Variance satisfies a Compatibility_Rule's
   `mathematical_condition` and that rule's `severity_level` is `Reserve`, THE
   Rule_Evaluator SHALL record a Risk_Zone with `localized_verdict = "Reserve"` and SHALL
   attach the rule's `explanation_message` to the Risk_Zone.

6. WHEN the computed Calculated_Variance does NOT satisfy any active Compatibility_Rule's
   `mathematical_condition` for a given Critical_Zone, THE Rule_Evaluator SHALL record no
   Risk_Zone for that zone.

7. THE Rule_Evaluator SHALL evaluate all Critical_Zones associated with the Model without
   stopping after the first incompatibility, so that the complete set of Risk_Zones is
   identified in a single pass.

8. IF a Critical_Zone's `zone_name` has no corresponding measurement field in the
   `AdjustmentResponse`, THE Rule_Evaluator SHALL skip that zone's rule evaluation and
   record a warning entry in the evaluation's `missing_data_log` without halting the
   evaluation of remaining zones.

9. IF the inputs are well-formed (measurement values are floats ≥ 0.0, rule conditions are
   syntactically valid), THEN THE Rule_Evaluator SHALL produce identical Risk_Zone sets,
   identical Calculated_Variance values, and identical `localized_verdict` values for
   every call with those same inputs (determinism property).

---

### Requirement 4: Morphology Compatibility Check

**User Story:** As an end user, I want the engine to factor in my body shape's
compatibility with the chosen garment model, so that I am warned when a model is
classified as unsuitable for my morphology even if the measurements technically fit.

#### Acceptance Criteria

1. WHEN all Critical_Zones have been evaluated, THE Verification_Engine SHALL query
   `MODEL_MORPHOLOGY_LINK` for a row matching the requested `model_id` and the provided
   `morphology_id`.

2. IF a `MODEL_MORPHOLOGY_LINK` row exists with `suitability_score = "Avoid"` for the
   requested `model_id` and `morphology_id`, THEN THE Verification_Engine SHALL add a
   morphology Risk_Zone entry with `localized_verdict = "Reserve"` or
   `localized_verdict = "Incompatible"` (determined by admin-configured morphology
   severity rules), a descriptive explanation message, `rule_id = null`, and
   `zone_id = null` (morphology incompatibility is model-level, not zone-scoped).

3. IF no `MODEL_MORPHOLOGY_LINK` row exists for the requested `model_id` and
   `morphology_id`, THEN THE Verification_Engine SHALL proceed to verdict aggregation
   without adding a morphology Risk_Zone and SHALL NOT treat the absence as an
   incompatibility.

4. IF a `MODEL_MORPHOLOGY_LINK` row exists with `suitability_score` of `Ideal` or
   `Flattering` for the requested `model_id` and `morphology_id`, THEN THE
   Verification_Engine SHALL NOT generate any Risk_Zone from morphology and MAY annotate
   the Verdict_Evaluation with the suitability score value for informational purposes.

5. IF the `MODEL_MORPHOLOGY_LINK` query fails with a database error, THEN THE
   Verification_Engine SHALL set Global_Status to `Failed`, persist the
   Verdict_Evaluation with the error cause in `missing_data_log`, and return HTTP 500 to
   the caller.

---

### Requirement 5: Global Verdict Aggregation

**User Story:** As an end user, I want to receive a single, clear overall verdict for the
combination I selected, so that I can immediately understand whether I can proceed with
ordering the garment.

#### Acceptance Criteria

1. WHEN all zone evaluations and morphology checks are complete, THE Verification_Engine
   SHALL compute the Global_Status using the following priority order: if any Risk_Zone
   has `localized_verdict = "Incompatible"`, the Global_Status SHALL be `Incompatible`;
   else if any Risk_Zone has `localized_verdict = "Reserve"`, the Global_Status SHALL be
   `Compatible_with_Reservations`; else the Global_Status SHALL be `Compatible`.

2. WHEN all zone evaluations and morphology checks are complete and no Risk_Zone was
   generated, THE Verification_Engine SHALL persist the Verdict_Evaluation with
   `global_status = "Compatible"` and return it to the caller with an empty `risk_zones`
   array.

3. IF the computed Global_Status is `Incompatible` but no Risk_Zone with
   `localized_verdict = "Incompatible"` exists at the time of persistence, THEN THE
   Verification_Engine SHALL raise an internal error, persist the Verdict_Evaluation with
   `global_status = "Failed"` and a log entry describing the invariant violation, and
   return HTTP 500 to the caller.

4. WHEN the Global_Status is `Indeterminate`, THE Verification_Engine SHALL persist a
   Verdict_Evaluation with `global_status = "Indeterminate"`, populate `missing_data_log`
   with the unmatched `cut_type` and `fabric_property` values, and return an empty
   `risk_zones` array to the caller.

5. WHEN the Global_Status is `Failed`, THE Verification_Engine SHALL persist a
   Verdict_Evaluation with `global_status = "Failed"` and populate `missing_data_log`
   with the specific failure cause: either the name of the missing input field or a
   description of the technical error encountered.

6. THE Verification_Engine SHALL produce exactly one Global_Status per evaluation
   request; returning multiple or ambiguous statuses for the same request is forbidden.

---

### Requirement 6: Mandatory Per-Zone Explanations

**User Story:** As an end user, I want to understand why each problematic zone was flagged,
so that I can make an informed decision about changing the fabric, the model, or adjusting
my measurements.

#### Acceptance Criteria

1. WHEN a Verdict_Evaluation has Global_Status `Incompatible` or
   `Compatible_with_Reservations`, THE Verification_Engine SHALL include in the response
   one Risk_Zone entry per violated Compatibility_Rule per affected Critical_Zone (i.e.
   for any Critical_Zone for which at least one active rule's condition evaluated to true),
   each entry containing the zone name, the violated rule identifier, the
   Calculated_Variance, the `localized_verdict` (one of `Incompatible` or `Reserve`), and
   the `explanation` text.

2. IF the Global_Status is `Incompatible` and no Risk_Zone with `localized_verdict =
   "Incompatible"` and a non-empty `explanation` field exists, THEN THE
   Verification_Engine SHALL raise an internal invariant error and return HTTP 500 rather
   than returning the explanation-free incompatible verdict to the caller.

3. WHEN the `explanation` field of a Compatibility_Rule is empty or null at rule-load
   time, THE Verification_Engine SHALL substitute a default explanation message built from
   the available fields: the zone name if non-null, otherwise the rule ID; the cut type
   if non-null, otherwise "unknown cut"; and the fabric property if non-null, otherwise
   "unknown fabric".

4. THE Verification_Engine SHALL return all Risk_Zones for the evaluation in a single
   response payload; partial or paginated zone explanations are not permitted for a single
   evaluation.

---

### Requirement 7: Evaluation Persistence and Audit Trail

**User Story:** As a catalog manager (admin), I want every compatibility evaluation to be
stored permanently, so that I can audit past decisions, trace which rule version was
applied, and support any future disputes about garment suitability.

#### Acceptance Criteria

1. WHEN an evaluation completes with any Global_Status (including `Indeterminate` and
   `Failed`), THE Verification_Engine SHALL persist the Verdict_Evaluation record to the
   `verdict_evaluations` table before returning the response to the caller.

2. WHEN an evaluation produces Risk_Zones, THE Verification_Engine SHALL persist each
   Risk_Zone to the `risk_zones` table with its `evaluation_id`, `rule_id`, `zone_id`,
   `calculated_variance`, `localized_verdict`, `explanation`, and `rule_version` fields
   populated, where `rule_version` is copied from the `version` field of the applied
   Compatibility_Rule at evaluation time.

3. WHEN persisting a Verdict_Evaluation, THE Verification_Engine SHALL store `client_id`,
   `model_id`, `fabric_id`, `measurements_id` (set to the value of `adjustment_id`), and
   `morphology_id` as non-nullable references.

4. WHEN an Admin updates a Compatibility_Rule after evaluations have been persisted, THE
   Verification_Engine SHALL NOT modify or recalculate any previously persisted
   Verdict_Evaluation or Risk_Zone record.

5. WHEN persisting a new Verdict_Evaluation, THE Verification_Engine SHALL assign a UUID
   generated by `uuid.uuid4()` as the `evaluation_id`.

6. THE Verification_Engine SHALL enforce uniqueness of `evaluation_id` in the
   `verdict_evaluations` table; if a collision occurs, the engine SHALL generate a new
   UUID and retry the insert once before returning HTTP 500.

7. WHEN persisting a Verdict_Evaluation and its Risk_Zones, THE Verification_Engine SHALL
   execute both writes within a single database transaction; if either write fails, the
   entire transaction SHALL be rolled back and the caller SHALL receive HTTP 500.

8. IF the database transaction for persisting the evaluation fails after rollback, THEN
   THE Verification_Engine SHALL return HTTP 500 with an error message identifying the
   persistence failure and SHALL NOT return a 201 response.

---

### Requirement 8: Stateless Rule Evaluation Core

**User Story:** As a backend developer, I want the rule evaluation core to be a pure,
stateless function, so that it is easily testable in isolation, reproducible, and does not
introduce hidden side effects into the compatibility verdict.

#### Acceptance Criteria

1. THE Rule_Evaluator SHALL be implemented as a pure function or stateless class that
   accepts as inputs: a list of active Compatibility_Rule records (each providing
   `rule_id`, `zone_id`, `mathematical_condition`, `severity_level`,
   `explanation_message`, `version`, `is_active = true`), a dict mapping zone names to
   their `adjusted_cm` float values, and a list of Critical_Zone identifiers associated
   with the Model; and returns a list of zero or more Risk_Zone-shaped records without
   performing any database access.

2. THE Rule_Evaluator SHALL NOT read from or write to the database, external services, or
   any mutable module-level state during rule evaluation.

3. IF all inputs are well-formed (measurement values are floats ≥ 0.0 and
   `mathematical_condition` strings are syntactically valid expressions), THEN THE
   Rule_Evaluator SHALL return the same Risk_Zone list for every invocation with those
   same inputs.

4. WHEN a Compatibility_Rule's `mathematical_condition` is syntactically malformed or
   uses an undefined variable, THE Rule_Evaluator SHALL skip that rule, append a warning
   to its return value describing the malformed condition and the affected `rule_id`, and
   continue evaluating remaining rules without raising an exception.

5. THE Rule_Evaluator SHALL be callable independently of the FastAPI request lifecycle,
   enabling unit testing without a running server or database connection.

---

### Requirement 9: Rule Administration API

**User Story:** As a catalog manager (admin), I want an API to create, update, activate,
and deactivate compatibility rules, so that I can manage thresholds without requiring a
code deployment.

#### Acceptance Criteria

1. WHEN an authenticated Admin submits a `POST /compatibility-rules` request with a valid
   body containing `cut_type`, `fabric_property`, `zone_id`, `mathematical_condition`
   (≤ 200 characters), `severity_level` (one of `Incompatible` or `Reserve`),
   `explanation_message` (≤ 500 characters), and `is_active`, THE Verification_Engine
   SHALL create the Compatibility_Rule with `version = 1`, persist it, and return HTTP
   201 with the new `rule_id` in the response body.

2. WHEN an authenticated Admin submits a `PATCH /compatibility-rules/{rule_id}` request,
   THE Verification_Engine SHALL allow updating only `mathematical_condition`,
   `severity_level`, `explanation_message`, and `is_active`; the fields `cut_type`,
   `fabric_property`, and `zone_id` SHALL be immutable after creation and any attempt to
   change them SHALL be rejected with HTTP 422.

3. WHEN an authenticated Admin successfully updates a Compatibility_Rule via `PATCH`, THE
   Verification_Engine SHALL increment the rule's `version` by 1 and return the updated
   rule in the response body.

4. WHEN an authenticated Admin requests `GET /compatibility-rules`, THE
   Verification_Engine SHALL return all Compatibility_Rules (active and inactive) with
   their `rule_id`, `cut_type`, `fabric_property`, `zone_id`, `severity_level`,
   `is_active`, and `version` fields; the response SHALL include at most 200 rules per
   call.

5. IF a non-Admin user attempts to call `POST /compatibility-rules`,
   `PATCH /compatibility-rules/{rule_id}`, or `GET /compatibility-rules`, THEN THE
   Verification_Engine SHALL return HTTP 403 and the response body SHALL NOT contain any
   `rule_id`, `mathematical_condition`, `severity_level`, or `explanation_message` values.

6. IF an Admin submits a `POST /compatibility-rules` request with a `(cut_type,
   fabric_property, zone_id)` combination that already exists in an active rule, THEN THE
   Verification_Engine SHALL return HTTP 409 and SHALL NOT create a duplicate rule.

7. IF an Admin submits a `PATCH /compatibility-rules/{rule_id}` request for a `rule_id`
   that does not exist, THEN THE Verification_Engine SHALL return HTTP 404.

---

### Requirement 10: Verification Request API

**User Story:** As Module 7 (Report), I want a single API endpoint to submit a
compatibility verification request and receive the complete verdict synchronously, so that
I can render the final report without polling or additional state management.

#### Acceptance Criteria

1. THE Verification_Engine SHALL expose a `POST /verifications` endpoint that accepts a
   JSON body containing `adjustment_id`, `model_id`, `fabric_id`, `morphology_id`, and
   `client_id`.

2. WHEN a verification request is submitted to `POST /verifications`, THE
   Verification_Engine SHALL return HTTP 201 with a response body containing
   `evaluation_id`, `global_status`, `created_at`, `fabric_recommendation`, and a
   `risk_zones` array.

3. WHEN a verification request fails input validation, THE Verification_Engine SHALL
   return HTTP 422 with a structured error body; HTTP 201 SHALL only be returned for
   evaluations that have been successfully persisted.

4. THE Verification_Engine SHALL expose a `GET /verifications/{evaluation_id}` endpoint
   that returns the persisted Verdict_Evaluation including all associated Risk_Zones and
   the `fabric_recommendation` field.

5. WHEN `GET /verifications/{evaluation_id}` is called with a non-existent
   `evaluation_id`, THE Verification_Engine SHALL return HTTP 404.

6. THE Verification_Engine SHALL implement all endpoints as `async def` handlers
   consistent with the project's FastAPI async patterns and SQLAlchemy async session via
   `get_db`.

---

### Requirement 11: Missing Rule Combination Handling (Indeterminate)

**User Story:** As a catalog manager (admin), I want to be alerted immediately when the
engine encounters a cut/fabric combination with no configured rule, so that I can add the
missing rule before users are blocked by an unresolvable indeterminate verdict.

#### Acceptance Criteria

1. WHEN the Verification_Engine loads rules for a given `cut_type` and `fabric_property`
   combination and finds zero active rules, THE Verification_Engine SHALL set the
   Global_Status to `Indeterminate` and SHALL NOT proceed to zone evaluation.

2. WHEN the Global_Status is set to `Indeterminate`, THE Verification_Engine SHALL persist
   the Verdict_Evaluation before returning the response, with `global_status =
   "Indeterminate"` and `missing_data_log` populated with the unmatched `cut_type` and
   `fabric_property` values.

3. WHEN the Verdict_Evaluation with `Indeterminate` status has been successfully
   persisted, THE Verification_Engine SHALL emit a structured log entry at ERROR level
   containing `cut_type`, `fabric_property`, `model_id`, and `fabric_id` so the Admin
   can identify and create the missing rule.

4. WHEN the Verification_Engine returns an `Indeterminate` result to the caller, THE
   Verification_Engine SHALL return HTTP 201 with `global_status = "Indeterminate"` and
   an empty `risk_zones` array; the status SHALL NOT be reported as `Compatible` or
   `Incompatible`.

---

### Requirement 12: Fabric Recommendation Level Check

**User Story:** As an end user, I want to know whether the fabric I chose is recommended
for the model I selected, so that I can be informed of official compatibility guidance
beyond just measurement fit.

#### Acceptance Criteria

1. WHEN zone evaluation and morphology checks are complete, THE Verification_Engine SHALL
   query `MODEL_FABRIC_LINK` for a row matching the requested `model_id` and `fabric_id`.

2. IF a `MODEL_FABRIC_LINK` row exists for the requested `model_id` and `fabric_id` with
   `recommendation_level` equal to `"Highly Recommended"` or `"Accepted"`, THEN THE
   Verification_Engine SHALL set the `fabric_recommendation` field in the
   Verdict_Evaluation response to the corresponding `recommendation_level` value without
   generating a Risk_Zone.

3. IF no `MODEL_FABRIC_LINK` row exists for the requested `model_id` and `fabric_id`,
   THEN THE Verification_Engine SHALL add a Risk_Zone entry with `localized_verdict =
   "Reserve"`, `explanation = "Fabric not listed as compatible with this model by the
   administrator"`, `rule_id = null`, and `zone_id = null`.

4. THE Verification_Engine SHALL include a `fabric_recommendation` field in every
   Verdict_Evaluation response; the field SHALL be set to the `recommendation_level`
   value when a `MODEL_FABRIC_LINK` row exists, or `null` when no link row exists.

---

### Requirement 13: Async and Project Convention Compliance

**User Story:** As a backend developer, I want Module 6 to follow the same async patterns
as Modules 3, 4, and 5, so that the codebase remains consistent and the module integrates
without friction into the existing FastAPI application.

#### Acceptance Criteria

1. THE Verification_Engine SHALL use `async def` for all FastAPI route handlers and all
   service layer functions that issue database queries, such that no synchronous call
   blocks the event loop.

2. THE Verification_Engine SHALL obtain database sessions via a `get_db` dependency that
   wraps `app.database.AsyncSessionLocal` and does not introduce a separate SQLAlchemy
   engine, consistent with the pattern used in `app.database`.

3. THE Verification_Engine SHALL define all ORM models inheriting from `app.database.Base`
   with UUID primary keys declared as `Column(UUID(as_uuid=True), primary_key=True,
   default=uuid.uuid4)`, where `uuid.uuid4` is passed as a callable reference, not a
   pre-called value.

4. THE Verification_Engine SHALL define all Pydantic request and response schemas as
   `BaseModel` subclasses using Pydantic v2; schemas that receive ORM model instances as
   input SHALL include `model_config = {"from_attributes": True}`.

5. THE Verification_Engine source files SHALL be placed inside
   `backend/app/modules/business_rules/` alongside Modules 5 and 7.

6. IF any Module 6 source file is placed outside `backend/app/modules/business_rules/`
   without explicit approval, THEN that placement SHALL be treated as a convention
   violation and flagged for correction during code review.

---

## Assumptions

1. Module 5 is operational and the `AdjustmentResponse` schema (including `adjustment_id`,
   `bust`, `waist`, `hips` with `adjusted_cm`) is stable at the time Module 6 is
   implemented.
2. Module 4 is operational and the `Model`, `CriticalZone`, and `ModelFabric` ORM entities
   are queryable via the shared async session.
3. Module 3 is operational and `Fabric` with `fabric_status` and `FabricCategory` with
   `reference_rigidity_level` are queryable via the shared async session.
4. The `MODEL_FABRIC_LINK` and `MODEL_MORPHOLOGY_LINK` association tables will be created
   as part of Module 6's migration; they are not yet present in the database.
5. The `compatibility_rules`, `verdict_evaluations`, and `risk_zones` tables do not exist
   yet and will be created by Module 6's migration scripts.
6. Morphology data (`morphology_id`) is provided by the caller (Module 7 or the client
   interface) referencing entities managed by Module 2's body shape classification.
7. Admin authentication and role-based access control (RBAC) are provided by Module 1;
   Module 6 depends on Module 1's auth middleware to protect admin endpoints.
8. The `mathematical_condition` field stores a string expression evaluated server-side by
   the Rule_Evaluator using safe expression parsing (e.g. `ratio > 1.4` where `ratio` is
   a named variable bound to the adjusted measurement value); arbitrary code execution via
   this field is explicitly out of scope.
9. Communication between modules is synchronous within the same FastAPI application; there
   is no message broker or event bus at this stage.
10. The admin alert for Indeterminate verdicts (Requirement 11.3) is implemented as a
    structured log entry; email or push notification delivery is out of scope for this
    module.
