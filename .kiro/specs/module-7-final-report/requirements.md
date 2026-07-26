# Requirements Document

## Introduction

Module 7 is the terminal aggregation layer of the Lova Fashion system. It consumes the
`compatibility.evaluated` event emitted by Module 6, creates an immutable `Rapport_mesure`
record that captures the exact state of the adjusted measurements, fabric, garment model,
verdict, and advice at generation time, and exposes that record through a structured JSON
API with display hints for the React / Tailwind CSS frontend.

The module also publishes a `report.saved` event to the shared in-process EventBus so that
Module 1 can archive the report reference in the client's profile history.

---

## Glossary

- **Report_Generator**: The Module 7 service component that subscribes to `compatibility.evaluated`, creates the `Rapport_mesure` record, and publishes `report.saved`.
- **Rapport_mesure**: The immutable database record representing one complete synthesis: adjusted measurements + verdict + advice + display hints for one (Measurement, Fabric, Garment Model) triple.
- **EventBus**: The shared in-process event bus singleton (`app.modules.auth_user_profile.events.bus.event_bus`) used for inter-module communication.
- **compatibility.evaluated**: The event published by Module 6 upon completion of a compatibility check. It carries CNI, adjustment_id, fabric_id, model_id, verdict, advice, and optionally incompatible_zones.
- **report.saved**: The event published by Module 7 after a `Rapport_mesure` is successfully persisted, consumed by Module 1's `handle_report_saved` handler.
- **Verdict**: The compatibility outcome string: exactly one of `"compatible"`, `"incompatible"`, or `"minor_adjustments"`.
- **adjusted_measurements**: A JSON snapshot (stored as JSONB) of Module 5's `measurement_adjustments` fields at report-generation time: `adjusted_bust_cm`, `adjusted_waist_cm`, `adjusted_hips_cm`, `bust_ease_cm`, `waist_ease_cm`, `hips_ease_cm`, `ease_source`.
- **incompatible_zones**: A structured list of objects `[{"zone": "<name>", "reason": "<text>"}]` included in the report when the verdict is `"incompatible"`.
- **display_hints**: A derived object returned in the API response (not persisted) containing `verdict_color` (`"green"` | `"orange"` | `"red"`) and `highlight_zones` (list of zone name strings).
- **Client**: The end user who commissioned the compatibility check and owns the resulting report. Identified by CNI.
- **Tailor**: An assigned service provider who may consult a client's report for cutting guidance.
- **Admin**: A platform administrator with elevated access rights.
- **CNI**: The 9-character national identity number used as the primary user identifier across the platform.

---

## Requirements

### Requirement 1: Event-Driven Report Creation

**User Story:** As the system, I want Module 7 to automatically create and persist a
`Rapport_mesure` record whenever Module 6 publishes a `compatibility.evaluated` event,
so that a complete synthesis is always available without any user action.

#### Acceptance Criteria

1. WHEN the EventBus delivers a `compatibility.evaluated` event, THE Report_Generator SHALL create and persist exactly one `Rapport_mesure` record containing: `cni`, `adjustment_id`, `fabric_id`, `model_id`, `verdict`, `advice`, `incompatible_zones` (nullable), `adjusted_measurements` (JSON snapshot), and `generated_at` set to the current UTC timestamp.

2. WHEN a `Rapport_mesure` is persisted successfully, THE Report_Generator SHALL publish a `report.saved` event to the EventBus with the payload `{"type": "report.saved", "cni": "<cni>", "report_id": "<id>", "date_generation": "<ISO timestamp>"}`.

3. THE Rapport_mesure SHALL be linked to exactly one `measurement_adjustments` record, exactly one `fabrics` record, and exactly one garment `models` record via non-nullable foreign keys.

4. THE Report_Generator SHALL snapshot the `adjusted_measurements` JSON at the moment of report creation so that the `Rapport_mesure` reflects the exact state of Module 5's data at `generated_at`, regardless of any subsequent changes to the source record.

5. THE Rapport_mesure SHALL be immutable after creation — THE Report_Generator SHALL NOT issue any UPDATE or DELETE statement against an existing `rapport_mesure` row.

---

### Requirement 2: Adjusted Measurements Snapshot

**User Story:** As a tailor, I want the report to include a structured snapshot of all
adjusted measurements at the time of generation, so that I can cut fabric based on values
that will never change.

#### Acceptance Criteria

1. WHEN a `Rapport_mesure` is created, THE Report_Generator SHALL read the `measurement_adjustments` record identified by `adjustment_id` and populate the `adjusted_measurements` field with a JSON object containing: `adjusted_bust_cm`, `adjusted_waist_cm`, `adjusted_hips_cm`, `bust_ease_cm`, `waist_ease_cm`, `hips_ease_cm`, and `ease_source`.

2. IF the `adjustment_id` from the event does not correspond to an existing `measurement_adjustments` row, THEN THE Report_Generator SHALL abort report creation, log an ERROR entry identifying the missing `adjustment_id`, and NOT persist any `Rapport_mesure` record.

3. IF any of `adjusted_bust_cm`, `adjusted_waist_cm`, or `adjusted_hips_cm` in the `measurement_adjustments` row is negative or NULL, THEN THE Report_Generator SHALL abort report creation, log an ERROR entry identifying the corrupt zone and its value, and NOT persist any `Rapport_mesure` record.

---

### Requirement 3: Verdict and Display Hints

**User Story:** As a client, I want the report to clearly indicate whether my chosen
fabric and garment model are compatible with my measurements, with colour-coded hints
for the frontend, so that I can understand the result at a glance.

#### Acceptance Criteria

1. WHEN the verdict in the `compatibility.evaluated` event is `"compatible"`, THE Report_Generator SHALL set `display_hints.verdict_color` to `"green"` and `display_hints.highlight_zones` to an empty list.

2. WHEN the verdict is `"minor_adjustments"`, THE Report_Generator SHALL set `display_hints.verdict_color` to `"orange"` and `display_hints.highlight_zones` to an empty list.

3. WHEN the verdict is `"incompatible"`, THE Report_Generator SHALL set `display_hints.verdict_color` to `"red"` and `display_hints.highlight_zones` to the list of zone names extracted from `incompatible_zones`.

4. WHEN the verdict is `"incompatible"`, THE Report_Generator SHALL persist the full `incompatible_zones` list (each item having `zone` and `reason` fields) in the `incompatible_zones` JSONB column of `rapport_mesure`.

5. IF the event `verdict` value is not exactly one of `"compatible"`, `"incompatible"`, or `"minor_adjustments"`, THEN THE Report_Generator SHALL abort report creation, log an ERROR entry, and NOT persist any record.

---

### Requirement 4: Upstream Data Validation Guards

**User Story:** As the system operator, I want report creation to be blocked and logged
whenever upstream data is missing or corrupt, so that invalid reports never reach users.

#### Acceptance Criteria

1. IF the `fabric_id` in the event does not correspond to an existing row in the `fabrics` table, THEN THE Report_Generator SHALL abort report creation, log an ERROR entry identifying the missing `fabric_id`, and NOT persist any record.

2. IF the `model_id` in the event does not correspond to an existing row in the `models` table, THEN THE Report_Generator SHALL abort report creation, log an ERROR entry identifying the missing `model_id`, and NOT persist any record.

3. IF the `cni` in the event does not correspond to an existing user in the `users` table, THEN THE Report_Generator SHALL abort report creation, log an ERROR entry identifying the missing CNI, and NOT persist any record.

4. WHEN the EventBus raises an exception during `report.saved` publication, THE Report_Generator SHALL log a WARNING entry and SHALL NOT rollback the already-committed `Rapport_mesure` record.

---

### Requirement 5: Retrieve a Specific Report

**User Story:** As a client or tailor, I want to retrieve the full details of a specific
report by its ID, so that I can review all adjusted measurements, verdict, advice, and
visual hints in one call.

#### Acceptance Criteria

1. WHEN an authenticated user calls `GET /reports/{report_id}`, THE Report_Generator SHALL return HTTP 200 with a `ReportResponse` payload containing: `report_id`, `cni`, `adjustment_id`, `fabric_id`, `model_id`, `verdict`, `advice`, `adjusted_measurements`, `incompatible_zones`, `display_hints`, and `generated_at`.

2. WHEN the `report_id` does not exist in the database, THE Report_Generator SHALL return HTTP 404.

3. WHEN the caller is a Client whose CNI does not match the `cni` on the report, THE Report_Generator SHALL return HTTP 403 Forbidden.

4. WHEN the caller is an authenticated Tailor or Admin, THE Report_Generator SHALL allow access to the report regardless of which client it belongs to.

5. WHEN the request carries no valid Bearer JWT, THE Report_Generator SHALL return HTTP 401 Unauthorized.

---

### Requirement 6: List Reports for the Authenticated Client

**User Story:** As a client, I want to view a history of all my past reports ordered
newest first, so that I can track how my combination choices have evolved over time.

#### Acceptance Criteria

1. WHEN an authenticated Client calls `GET /reports/me`, THE Report_Generator SHALL return HTTP 200 with a list of `ReportSummary` objects for all reports whose `cni` matches the caller's CNI, ordered by `generated_at` descending.

2. WHEN no reports exist for the authenticated Client, THE Report_Generator SHALL return HTTP 200 with an empty `reports` array and `total: 0`.

3. THE Report_Generator SHALL include in each `ReportSummary`: `report_id`, `verdict`, `display_hints.verdict_color`, `fabric_id`, `model_id`, and `generated_at`.

4. WHEN the request carries no valid Bearer JWT, THE Report_Generator SHALL return HTTP 401 Unauthorized.

---

### Requirement 7: Retrieve Reports for a Specific Client by Tailor or Admin

**User Story:** As a tailor or admin, I want to retrieve all reports for a specific client
by CNI, so that I can advise the client based on the full history of their compatibility
checks.

#### Acceptance Criteria

1. WHEN an authenticated Tailor or Admin calls `GET /reports/client/{cni}`, THE Report_Generator SHALL return HTTP 200 with a list of `ReportSummary` objects for the target client, ordered by `generated_at` descending.

2. WHEN no reports exist for the specified CNI, THE Report_Generator SHALL return HTTP 200 with an empty `reports` array and `total: 0`.

3. WHEN the caller role is Client, THE Report_Generator SHALL return HTTP 403 Forbidden.

4. WHEN the specified CNI does not correspond to any user in the system, THE Report_Generator SHALL return HTTP 404.

5. WHEN the request carries no valid Bearer JWT, THE Report_Generator SHALL return HTTP 401 Unauthorized.

---

### Requirement 8: Report Immutability

**User Story:** As an auditor, I want every report to permanently reflect the exact state
of data at the moment it was generated, so that historical records are never altered.

#### Acceptance Criteria

1. THE Report_Generator SHALL NOT expose any endpoint or internal path that modifies an existing `Rapport_mesure` record — no PUT, PATCH, or DELETE routes are permitted.

2. WHEN a second `compatibility.evaluated` event arrives for the same `(cni, adjustment_id, fabric_id, model_id)` combination, THE Report_Generator SHALL create a new distinct `Rapport_mesure` record with a new UUID and new `generated_at` timestamp rather than overwriting the existing record.

---

### Requirement 9: Outbound Event Publishing

**User Story:** As Module 1, I want to receive a `report.saved` event after each report is
created, so that I can archive the report reference in the client's profile history without
polling the database.

#### Acceptance Criteria

1. WHEN a `Rapport_mesure` is successfully committed to the database, THE Report_Generator SHALL publish exactly one `report.saved` event to the EventBus.

2. THE `report.saved` event SHALL carry the payload `{"type": "report.saved", "cni": "<user_cni>", "report_id": "<report_id>", "date_generation": "<ISO 8601 UTC timestamp>"}` matching exactly the contract expected by Module 1's `handle_report_saved` handler.

3. IF EventBus publication fails after a successful DB commit, THE Report_Generator SHALL log a WARNING and SHALL NOT raise an exception that would trigger duplicate DB writes.

---

## Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-01 | The `compatibility.evaluated` event handler SHALL complete (DB write + EventBus publish attempt) within 2 seconds under normal conditions. |
| NFR-02 | All HTTP API endpoints require `Authorization: Bearer <JWT>`. |
| NFR-03 | The `rapport_mesure` table has no UPDATE RLS policy — Row-Level Security enforces immutability at the DB level for client-scoped reads. |
| NFR-04 | `adjusted_measurements` is stored as JSONB and returned as a structured object in all API responses. |
| NFR-05 | All error responses follow the `{"detail": "<message>"}` envelope consistent with other modules. |
| NFR-06 | `generated_at` uses `TIMESTAMPTZ` and is always set server-side via `DEFAULT now()` — clients cannot supply this value. |
