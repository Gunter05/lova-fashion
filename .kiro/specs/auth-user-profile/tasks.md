# Implementation Plan: Module 1 — Authentication & User Profile

## Overview

This plan breaks Module 1 into seven implementation phases, each mapping directly
to a logical sub-system or concern. All code lives under
`backend/app/modules/auth_catalogues/`. The stack is Python 3.11 + FastAPI,
PostgreSQL via Supabase, Supabase Storage, and Hypothesis for property-based tests.

Tasks are ordered so each step can compile and run before the next begins.
Test sub-tasks are marked `*` (optional for a fast MVP) but must pass before the
module is marked ready for review.

---

## Tasks

### Phase 1 — Project Scaffolding

- [x] 1. Scaffold the `auth_catalogues` package structure
  - Create all `__init__.py` stubs, sub-packages (`auth/`, `profile/`, `measurement/`, `events/`), and empty module files listed in the design's Internal Package Layout section.
  - Create `backend/app/modules/auth_catalogues/router.py` that instantiates a top-level `APIRouter` and will later mount the three sub-routers.
  - Wire the top-level router into `backend/main.py` so `GET /` returns 200 (smoke test).
  - Create `backend/app/modules/auth_catalogues/auth/dependencies.py` with stub signatures for `get_current_user` and `require_role` (raise `NotImplementedError` for now).
  - _Requirements: all — foundational scaffolding_
  - _Design: Internal Package Layout_

- [x] 2. Create the database migration script
  - Write `backend/app/db/migrations/001_module1_schema.sql` containing the exact DDL from the design: `user_role` enum, `users`, `photo_profil`, `mensuration`, `rapport_archive`, `token_denylist`, `tailor_client_assignment` tables with all CHECK constraints, UNIQUE constraints, and indexes.
  - Add a `backend/app/db/session.py` module that exposes an async SQLAlchemy engine + `AsyncSession` factory configured from the `DATABASE_URL` environment variable.
  - _Requirements: 1.1, 2.1, 3.1, 7.1, 8.1, 9.1, 12.1_
  - _Design: Data Models — PostgreSQL Table Definitions_

- [x] 3. Define Pydantic schemas for all three sub-services
  - `auth/schemas.py`: `RegisterRequest`, `RegisterResponse`, `LoginRequest`, `LoginResponse`, `ErrorResponse`, `MultiFieldErrorResponse`.
  - `profile/schemas.py`: `UserProfileResponse`, `UpdateProfileRequest`, `PhotoProfilResponse`, `AdminUserResponse`, `RoleUpdateRequest`.
  - `measurement/schemas.py`: `MensurationCreateRequest`, `MensurationResponse`, `MensurationListResponse`.
  - All fields must carry Pydantic validators that enforce the constraints from the requirements (CNI regex `^[A-Za-z0-9]{9}$`, email format, password min-length 8, nom max-length 100, measurement range 0 < x ≤ 300).
  - _Requirements: 1.4–1.9, 6.3–6.8, 8.3–8.4_
  - _Design: API Endpoints — request/response tables; Error Handling_

- [x] 4. Checkpoint — smoke test
  - Run `pytest backend/tests/test_smoke.py` (create the file): assert that `GET /` returns 200, the top-level router mounts without error, and all schema classes import cleanly.
  - Ensure all tests pass, ask the user if questions arise.


---

### Phase 2 — Data Layer

- [x] 5. Implement SQLAlchemy ORM models
  - Create `backend/app/db/models.py` with `UserModel`, `PhotoProfilModel`, `MensurationModel`, `RapportArchiveModel`, `TokenDenylistModel`, `TailorClientAssignmentModel` mapped to the tables defined in task 2.
  - Each model exposes only the columns defined in the DDL; no extra columns.
  - _Requirements: 1.1, 7.1, 8.1, 9.1, 12.1_
  - _Design: Data Models_

- [x] 6. Implement repository layer — `UserRepository`
  - Create `auth_catalogues/auth/repository.py` with async methods: `create_user`, `get_by_email`, `get_by_cni`, `set_is_active`.
  - `create_user` raises a typed `DuplicateCNIError` or `DuplicateEmailError` on constraint violation (maps to HTTP 409).
  - _Requirements: 1.1–1.3, 2.3, 13.6_
  - _Design: Data Models; API Endpoints_

- [x] 7. Implement repository layer — `ProfileRepository`
  - Create `auth_catalogues/profile/repository.py` with async methods: `get_user`, `update_user`, `list_users`, `add_photo`, `get_photos`, `add_rapport`, `get_rapports`, `is_tailor_assigned`.
  - _Requirements: 6.1–6.8, 7.1–7.9, 12.1–12.5, 13.1–13.7_
  - _Design: Data Models_

- [x] 8. Implement repository layer — `MensurationRepository`
  - Create `auth_catalogues/measurement/repository.py` with async methods: `create_mensuration`, `get_history_for_cni`, `exists_event_hash`.
  - `create_mensuration` accepts an optional `source_event_hash`; when provided, checks uniqueness before inserting (idempotency guard).
  - _Requirements: 8.1–8.6, 9.1–9.5, 10.1–10.5_
  - _Design: Data Models — source_event_hash note_

- [x] 9. Implement `TokenDenylistRepository`
  - Add `add_jti(jti, expires_at)` and `is_jti_denied(jti)` async methods in `auth_catalogues/auth/repository.py`.
  - _Requirements: 3.1–3.5, 4.5_
  - _Design: Authentication & Security Design — Token Validation Flow_


---

### Phase 3 — Auth_Service

- [x] 10. Implement `security.py` — bcrypt and JWT helpers
  - Write `auth/security.py` with:
    - `hash_password(plaintext: str) -> str` using `passlib[bcrypt]` with cost factor 12.
    - `verify_password(plaintext: str, hashed: str) -> bool`.
    - `issue_token(cni: str, role: str) -> str` producing a HS256 JWT with claims `iss`, `sub`, `cni`, `role`, `iat`, `exp` (iat + 86400), `jti` (uuid4).
    - `decode_token(token: str) -> dict` verifying signature, `iss`, and required claims; raises typed exceptions on failure.
  - Store `JWT_SECRET` and `JWT_ISSUER` from environment variables; never log or return them.
  - _Requirements: 1.10, 2.1–2.2, 4.1–4.6_
  - _Design: Authentication & Security Design — JWT Structure, Password Security_

  - [ ]* 10.1 Write property test — Property 1: Password hashing irreversibility
    - File: `backend/tests/test_security.py`
    - Strategy: `st.text(min_size=8)` for passwords, `st.text(min_size=8)` for a second distinct password.
    - Assert `hash_password(p) != p`, `verify_password(p, hash_password(p)) is True`, and `verify_password(p1, hash_password(p2)) is False` for all `p1 != p2`.
    - `settings(max_examples=100)`
    - **Property 1: Password Hashing — Irreversibility and Round-Trip Verify**
    - **Validates: Requirements 1.10, 2.1**

  - [ ]* 10.2 Write property test — Property 3: JWT encode/decode round-trip
    - File: `backend/tests/test_jwt.py`
    - Strategy: `st.from_regex(r'[A-Za-z0-9]{9}')` for CNI, `st.sampled_from(['Client','Tailor','Admin'])` for role.
    - Assert `decode_token(issue_token(cni, role)).cni == cni`, `.role == role`, and `exp - iat == 86400`.
    - **Property 3: JWT Encode/Decode Round-Trip**
    - **Validates: Requirements 2.1, 2.2, 4.2**

- [x] 11. Implement in-memory rate-limiter
  - Write `auth/rate_limit.py` with `RateLimiter` class tracking per-email failed attempts in a `dict`.
  - `record_failure(email)` increments the counter with a rolling 15-minute window.
  - `is_locked(email) -> bool` returns `True` when ≥ 5 failures within the window.
  - `reset(email)` clears the counter on successful login.
  - `retry_after(email) -> int` returns remaining seconds in the window.
  - _Requirements: 2.7_
  - _Design: Authentication & Security Design — Rate Limiting_

  - [ ]* 11.1 Write property test — Property 9: Rate-limiting enforcement
    - File: `backend/tests/test_rate_limit.py`
    - Strategy: `st.integers(min_value=5, max_value=20)` for failure count.
    - Assert every attempt after the 5th failure within 15 min returns `is_locked == True`.
    - **Property 9: Login Rate-Limiting Enforcement**
    - **Validates: Requirements 2.7**


- [x] 12. Implement `Auth_Service` business logic
  - Write `auth/service.py` with:
    - `register_user(data: RegisterRequest) -> RegisterResponse` — hashes password, calls `UserRepository.create_user`, never stores plaintext.
    - `login_user(data: LoginRequest) -> LoginResponse` — checks `is_locked`, verifies credentials, checks `is_active`, calls `issue_token`, calls `reset`, publishes `user.authenticated` via EventBus (fire-and-forget; catches `EventBusError` and logs it without blocking the response).
    - `logout_user(token_claims, raw_token) -> None` — adds `jti` to denylist.
  - _Requirements: 1.1–1.10, 2.1–2.8, 3.1–3.4, 13.6_
  - _Design: Components and Interfaces; Authentication & Security Design_

- [x] 13. Implement `get_current_user` and `require_role` dependencies
  - Complete `auth/dependencies.py`:
    - `get_current_user` extracts Bearer token, calls `decode_token`, checks `token_denylist`, returns `UserClaims(cni, role)`.
    - `require_role(*roles)` returns a FastAPI dependency that raises HTTP 403 if `current_user.role not in roles`.
  - _Requirements: 4.1–4.6, 5.6_
  - _Design: Key Dependency Interfaces; Token Validation Flow_

- [x] 14. Implement Auth HTTP router
  - Write `auth/router.py` mounting `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`.
  - Each handler delegates to `Auth_Service`; maps typed exceptions to the error envelope defined in the design (`SCREAMING_SNAKE_CASE` error codes).
  - Mount `auth_router` in the top-level `router.py`.
  - _Requirements: 1.1–1.10, 2.1–2.8, 3.1–3.4_
  - _Design: API Endpoints — Authentication Endpoints_

  - [ ]* 14.1 Write property test — Property 2: CNI/email uniqueness cardinality invariant
    - File: `backend/tests/test_registration.py`
    - Strategy: `st.from_regex(r'[A-Za-z0-9]{9}')` for CNI, `st.emails()` for email, `st.integers(min_value=2, max_value=5)` for registration attempt count.
    - Assert that after N attempts with the same CNI or email, exactly 1 user record exists and all subsequent attempts return 409.
    - **Property 2: CNI and Email Uniqueness — Cardinality Invariant**
    - **Validates: Requirements 1.2, 1.3, 6.5**

  - [ ]* 14.2 Write property test — Property 10: Logout idempotence and post-logout denial
    - File: `backend/tests/test_logout.py`
    - Strategy: `st.integers(min_value=1, max_value=5)` for logout repeat count.
    - Assert that repeated `POST /auth/logout` with the same token returns 200 each time, and any subsequent request to a protected endpoint with the same token returns 401. `token_denylist` contains exactly one row for the token's `jti`.
    - **Property 10: Logout Idempotence and Post-Logout Access Denial**
    - **Validates: Requirements 3.1, 3.2, 3.5**

- [x] 15. Checkpoint — Auth_Service
  - Run `pytest backend/tests/test_auth_register.py backend/tests/test_auth_login.py backend/tests/test_security.py backend/tests/test_jwt.py backend/tests/test_logout.py`.
  - Ensure all tests pass, ask the user if questions arise.


---

### Phase 4 — Profile_Service

- [x] 16. Implement `Profile_Service` business logic
  - Write `profile/service.py` with:
    - `get_profile(cni: str) -> UserProfileResponse`.
    - `update_profile(cni: str, data: UpdateProfileRequest) -> UserProfileResponse` — rejects `cni`, `date_inscription` (HTTP 422), rejects `role` for non-Admin (HTTP 403), validates email format and nom length.
    - `upload_photo(cni: str, file: UploadFile) -> PhotoProfilResponse` — validates MIME type, non-zero size, and ≤ 5 MB; calls Supabase Storage upload; on `StorageUnavailableError` returns HTTP 503 without persisting a `PhotoProfil` record.
    - `get_photo_history(cni: str) -> list[PhotoProfilResponse]` — ordered `date_upload DESC`.
    - `get_report_history(cni: str) -> list[RapportArchiveResponse]` — ordered `archived_at DESC`.
  - _Requirements: 6.1–6.8, 7.1–7.9, 12.5_
  - _Design: Components and Interfaces; API Endpoints — Profile Endpoints_

  - [ ]* 16.1 Write property test — Property 6: Profile photo append-only invariant
    - File: `backend/tests/test_photo_upload.py`
    - Strategy: `st.integers(min_value=0, max_value=10)` for initial photo count `k`.
    - Seed the DB with `k` photos, upload one more, assert exactly `k+1` records exist and all original `url_photo`/`date_upload` values are unchanged.
    - **Property 6: Profile Photo History — Append-Only Invariant**
    - **Validates: Requirements 7.4, 7.1**

- [x] 17. Implement Admin operations in `Profile_Service`
  - Add to `profile/service.py`:
    - `list_all_users() -> list[AdminUserResponse]`.
    - `update_user_role(target_cni: str, new_role: Role, requester_role: Role) -> AdminUserResponse` — raises HTTP 403 if target is Admin.
    - `deactivate_user(target_cni: str) -> None` — idempotent: if already inactive, returns 200 without modifying the record.
  - _Requirements: 13.1–13.7_
  - _Design: API Endpoints — Admin Endpoints_

- [x] 18. Implement Profile and Admin HTTP routers
  - Write `profile/router.py` mounting:
    - `GET /users/me`, `PATCH /users/me`, `POST /users/me/photos`, `GET /users/me/photos`, `GET /users/me/reports` (requires `get_current_user`).
    - `GET /admin/users`, `PATCH /admin/users/{cni}/role`, `PATCH /admin/users/{cni}/deactivate` (requires `require_role(Role.Admin)`).
  - Map all typed service exceptions to the error envelope.
  - Mount `profile_router` in the top-level `router.py`.
  - _Requirements: 5.1–5.6, 6.1–6.8, 7.1–7.9, 13.1–13.7_
  - _Design: API Endpoints — Profile Endpoints, Admin Endpoints_

  - [ ]* 18.1 Write property test — Property 7: RBAC authorisation consistency
    - File: `backend/tests/test_rbac.py`
    - Strategy: `st.sampled_from(Role)` × `st.sampled_from(protected_endpoints)` where `protected_endpoints` is a list of `(method, path, authorised_roles)` tuples.
    - Assert every request from a User whose role is not in `authorised_roles` returns 403, regardless of other User attributes.
    - `settings(max_examples=100)`
    - **Property 7: Role-Based Access — Authorisation Consistency**
    - **Validates: Requirements 5.4, 5.5, 5.6, 13.4**

- [x] 19. Checkpoint — Profile_Service
  - Run `pytest backend/tests/test_profile.py backend/tests/test_admin.py backend/tests/test_photo_upload.py backend/tests/test_rbac.py`.
  - Ensure all tests pass, ask the user if questions arise.


---

### Phase 5 — Measurement_Service

- [x] 20. Implement `Measurement_Service` business logic
  - Write `measurement/service.py` with:
    - `create_manual_mensuration(cni: str, data: MensurationCreateRequest) -> MensurationResponse` — validates all five values > 0 and ≤ 300; on any invalid value rejects the entire request with HTTP 422 listing every offending field; on failure to return an error response logs CRITICAL and rolls back (Req 8.5).
    - `get_history(cni: str, requester_cni: str, requester_role: Role) -> list[MensurationResponse]` — enforces Tailor assignment check (HTTP 403 if not assigned); returns records ordered `date_mensuration DESC`.
  - _Requirements: 8.1–8.6, 10.1–10.5_
  - _Design: API Endpoints — Measurement Endpoints_

  - [ ]* 20.1 Write property test — Property 4: Measurement exhaustive bad-input rejection
    - File: `backend/tests/test_measurement_validation.py`
    - Strategy: generate a dict of 5 measurement values where at least one is drawn from `st.floats(max_value=0.0)` or `st.floats(min_value=300.01)`.
    - Assert every such request is rejected with HTTP 422 and no `mensuration` row is created.
    - `settings(max_examples=100)`
    - **Property 4: Measurement Validation — Exhaustive Bad-Input Rejection**
    - **Validates: Requirements 8.3, 8.4, 9.2**

  - [ ]* 20.2 Write property test — Property 5: Mensuration history ordering and completeness
    - File: `backend/tests/test_measurement_history.py`
    - Strategy: `st.lists(st.datetimes(), min_size=2)` to drive insertion order (insert n records in arbitrary order).
    - Assert the history endpoint returns exactly n records and `entries[i].date_mensuration >= entries[i+1].date_mensuration` for all i.
    - **Property 5: Mensuration History Ordering and Completeness**
    - **Validates: Requirements 10.1, 10.2, 10.4**

- [x] 21. Implement Measurement HTTP router
  - Write `measurement/router.py` mounting:
    - `POST /users/me/mensurations` (requires `require_role(Role.Client)`).
    - `GET /users/me/mensurations` (requires `require_role(Role.Client)`).
    - `GET /users/{cni}/mensurations` (requires `require_role(Role.Tailor, Role.Admin)`).
  - Map exceptions to the error envelope; return 404 when target CNI not found.
  - Mount `measurement_router` in the top-level `router.py`.
  - _Requirements: 8.1–8.6, 10.1–10.5_
  - _Design: API Endpoints — Measurement Endpoints_

- [x] 22. Checkpoint — Measurement_Service
  - Run `pytest backend/tests/test_measurement_validation.py backend/tests/test_measurement_history.py`.
  - Ensure all tests pass, ask the user if questions arise.


---

### Phase 6 — Event Bus

- [x] 23. Implement the in-process `EventBus`
  - Write `events/bus.py` with the `EventBus` class as specified in the design (subscribe / publish / per-handler exception isolation with `logger.error`).
  - Instantiate a module-level singleton `event_bus = EventBus()` consumed by all publishers and handlers.
  - _Requirements: 2.5, 2.8, 9.1–9.5, 11.1–11.4, 12.1–12.4_
  - _Design: Event Bus Design — MVP Implementation_

- [x] 24. Implement event publishers
  - Write `events/publishers.py`:
    - `publish_user_authenticated(bus, cni, role, authenticated_at)` — publishes `user.authenticated` event (Req 2.5; if bus unavailable, log and return — Req 2.8).
    - `publish_user_profile_data(bus, cni, mensurations)` — publishes `user.profile_data`.
    - `publish_user_profile_data_error(bus, cni, reason)` — publishes `user.profile_data.error`.
  - Call `publish_user_authenticated` from `Auth_Service.login_user` (update task 12).
  - _Requirements: 2.5, 2.8, 11.1–11.4_
  - _Design: Event Bus Design — Event Payload Schemas_

- [x] 25. Implement event handlers
  - Write `events/handlers.py`:
    - `handle_measurements_estimated(payload)` — validates all five measurement fields present, values > 0 and ≤ 300; computes `source_event_hash`; calls `MensurationRepository.exists_event_hash` — if duplicate, logs WARNING and discards; if CNI not found, logs ERROR and discards; otherwise persists via `MensurationRepository.create_mensuration`.
    - `handle_report_saved(payload)` — validates CNI exists; calls `ProfileRepository.add_rapport` (unique constraint handles idempotency); if CNI unknown, logs ERROR and discards.
    - `handle_profile_data_request(payload)` — retrieves latest (or session-selected) mensuration for CNI; publishes `user.profile_data` or `user.profile_data.error`.
  - Register all three handlers in `router.py` (or FastAPI `lifespan`) via `event_bus.subscribe(...)`.
  - _Requirements: 9.1–9.5, 11.1–11.4, 12.1–12.4_
  - _Design: Internal Event Handlers and Publishers_

  - [ ]* 25.1 Write property test — Property 8: Measurement event idempotence guard
    - File: `backend/tests/test_event_idempotence.py`
    - Strategy: `st.integers(min_value=1, max_value=5)` for re-delivery count.
    - Deliver the same `measurements.estimated` payload N times; assert exactly 1 `mensuration` row exists for that CNI/hash.
    - **Property 8: Measurement Event Idempotence Guard**
    - **Validates: Requirements 9.5**

  - [ ]* 25.2 Write property test — Property 11: Report archive idempotence
    - File: `backend/tests/test_report_archive.py`
    - Strategy: `st.integers(min_value=1, max_value=5)` for re-delivery count.
    - Deliver the same `report.saved` payload N times; assert exactly 1 `rapport_archive` row for that `(cni, report_id)`.
    - **Property 11: Report Archive Idempotence**
    - **Validates: Requirements 12.4**

- [x] 26. Checkpoint — Event Bus
  - Run `pytest backend/tests/test_event_handlers.py backend/tests/test_event_idempotence.py backend/tests/test_report_archive.py`.
  - Ensure all tests pass, ask the user if questions arise.


---

### Phase 7 — Tests

- [x] 27. Write unit / example-based tests — Auth_Service
  - File: `backend/tests/test_auth_register.py` — valid registration flow; each 409 and 422 error path (duplicate CNI, duplicate email, missing fields, invalid CNI format, invalid email, password < 8 chars, nom > 100 chars, invalid role).
  - File: `backend/tests/test_auth_login.py` — successful login, wrong password, unknown email, deactivated account, missing fields, lockout after 5 failures.
  - File: `backend/tests/test_logout.py` (example tests) — logout with valid token, expired token, missing token, double logout.
  - _Requirements: 1.1–1.10, 2.1–2.8, 3.1–3.5_
  - _Design: Testing Strategy — Unit / Example-Based Tests_

- [x] 28. Write unit / example-based tests — Profile_Service and Admin
  - File: `backend/tests/test_profile.py` — GET profile, PATCH profile (success, email conflict, nom too long, empty body, immutable field, role change by non-Admin), photo upload (success, wrong MIME, empty file, > 5 MB, storage unavailable), photo history (populated and empty).
  - File: `backend/tests/test_admin.py` — list users, role update (success, Admin-on-Admin rejection, invalid role), deactivate (success, idempotent, non-Admin attempt).
  - _Requirements: 5.1–5.6, 6.1–6.8, 7.1–7.9, 13.1–13.7_
  - _Design: Testing Strategy — Unit / Example-Based Tests_

- [x] 29. Write unit / example-based tests — Measurement_Service and Event handlers
  - File: `backend/tests/test_measurement_history.py` (example tests) — valid creation, forbidden Tailor attempt, empty history, full field set in response.
  - File: `backend/tests/test_event_handlers.py` — `measurements.estimated` handler (valid, missing field, unknown CNI, duplicate hash), `report.saved` handler (valid, unknown CNI, duplicate report_id), `profile_data_request` handler (success, no measurements, unknown CNI).
  - _Requirements: 8.1–8.6, 9.1–9.5, 10.1–10.5, 11.1–11.4, 12.1–12.5_
  - _Design: Testing Strategy — Unit / Example-Based Tests_

- [x] 30. Final checkpoint — full test suite
  - Run `pytest backend/tests/ --tb=short -q`.
  - Statement coverage must be ≥ 85 % for `auth/`, `profile/`, `measurement/` packages.
  - All 11 property tests must pass with `max_examples=100`.
  - Ensure all tests pass, ask the user if questions arise.


---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP, but all 11 property tests must pass before the module is submitted for review.
- Every task references specific requirements (e.g., "Req 1 AC 1–10") and the design section it follows.
- Checkpoints validate incremental correctness; do not advance to the next phase with failing tests.
- The `source_event_hash` unique constraint in the `mensuration` table is the database-level idempotency guard for Property 8 (Req 9.5).
- Rate-limiter uses an in-memory dict for MVP. When moving to multi-worker production on Render, replace with a Redis key (see design Upgrade path note).
- SQLite is used for unit/property tests; integration tests tagged `@pytest.mark.integration` run against the real Supabase `lova_test` project in CI only.
- Branch for this module: `feature/auth-catalogues` (never push directly to `main`).

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "2"] },
    { "id": 1, "tasks": ["3"] },
    { "id": 2, "tasks": ["5"] },
    { "id": 3, "tasks": ["6", "7", "8", "9"] },
    { "id": 4, "tasks": ["10", "11"] },
    { "id": 5, "tasks": ["10.1", "10.2", "11.1", "12"] },
    { "id": 6, "tasks": ["13", "14"] },
    { "id": 7, "tasks": ["14.1", "14.2", "16"] },
    { "id": 8, "tasks": ["16.1", "17"] },
    { "id": 9, "tasks": ["18"] },
    { "id": 10, "tasks": ["18.1", "20"] },
    { "id": 11, "tasks": ["20.1", "20.2", "21"] },
    { "id": 12, "tasks": ["23"] },
    { "id": 13, "tasks": ["24", "25"] },
    { "id": 14, "tasks": ["25.1", "25.2"] },
    { "id": 15, "tasks": ["27", "28", "29"] }
  ]
}
```
