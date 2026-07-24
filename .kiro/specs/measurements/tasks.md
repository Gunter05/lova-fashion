# Tasks — Module 2: Photo Capture & Measurement Estimation
# (Prise de mesure — Liste des tâches d'implémentation)

Each task references the Story (US-xx) and Acceptance Criterion (AC-xx.x) it implements.
Tasks are ordered for sequential execution — later tasks depend on earlier ones.

---

## Phase 0 — Project Setup

- [ ] **T-00.1** Add required packages to `backend/requirements.txt`:
  `mediapipe==0.10.14`, `opencv-python-headless==4.10.0.84`, `numpy==1.26.4`,
  `python-multipart==0.0.9`, `supabase==2.9.1`.
  > _No story dependency — prerequisite for all CV tasks._

- [ ] **T-00.2** Create the module directory structure under
  `backend/app/modules/measurements/`:
  `__init__.py`, `router.py`, `service.py`, `estimation.py`, `classification.py`,
  `schemas.py`, `models.py`, `storage.py`, `dependencies.py`.
  > _Design §2._

- [ ] **T-00.3** Register the measurements router in `backend/main.py`
  at prefix `/api/v1/measurements`.
  > _Design §5._

---

## Phase 1 — Database & Migrations

- [ ] **T-01.1** Write and execute the SQL migration for the `body_shapes` reference table
  (columns: `code`, `name`, `description`) and seed the 5 rows
  (`HOURGLASS`, `PEAR`, `INVERTED_TRIANGLE`, `APPLE`, `RECTANGLE`).
  > _AC-08.1 · Design §3.3_

- [ ] **T-01.2** Write and execute the SQL migration for the `capture_sessions` table:
  columns, `CHECK` constraint on `status`, `DECIMAL(5,1)` constraint on `entered_stature`,
  `updated_at` trigger, partial unique index `uix_one_active_per_user`, RLS policy.
  > _AC-01.2, AC-01.3, AC-03.1, NFR-04 · Design §3.1_

- [ ] **T-01.3** Write and execute the SQL migration for the `raw_measurements` table:
  `UNIQUE` constraint on `session_id`, FK to `body_shapes`, RLS policy.
  > _AC-08.2, NFR-04 · Design §3.2_

---

## Phase 2 — ORM Models & Schemas

- [ ] **T-02.1** Implement SQLAlchemy ORM model `CaptureSession` in `models.py`
  mapping all columns from `capture_sessions`.
  > _Design §3.1_

- [ ] **T-02.2** Implement SQLAlchemy ORM model `RawMeasurement` in `models.py`
  mapping all columns from `raw_measurements`, with FK relationship to `CaptureSession`.
  > _Design §3.2_

- [ ] **T-02.3** Implement all Pydantic schemas in `schemas.py`:
  `SessionCreateResponse`, `StatureUpdateRequest`, `ProcessTriggerResponse`,
  `MeasurementResult`, `SessionStatusResponse`, `SessionListItem`.
  > _Design §4_

---

## Phase 3 — Storage Adapter

- [ ] **T-03.1** Implement `SupabaseStorageAdapter` in `storage.py` with two methods:
  - `upload(user_id, session_id, view, file_bytes, mime_type) → str` (returns public URL)
  - `download(url) → bytes`
  Storage path must follow `captures/{user_id}/{session_id}/front.jpg` (or `profile.jpg`).
  > _AC-02.5 · Design §9_

- [ ] **T-03.2** Verify that the Supabase Storage bucket RLS policy
  (`auth.uid()::text = (storage.foldername(name))[1]`) is active on the `captures` bucket.
  Document the verification step in a comment inside `storage.py`.
  > _NFR-04 · Design §9_

---

## Phase 4 — Computer Vision Pipeline

- [ ] **T-04.1** Implement `MeasurementEstimationService.estimate()` in `estimation.py` —
  Step 1 (front landmark detection via MediaPipe Pose, `static_image_mode=True`).
  Raise `BodyNotDetectedError` if `pose_landmarks` is `None` or landmark confidence < 0.5.
  > _AC-02.4, AC-04.1 · Design §6.2 steps 1 & 3_

- [ ] **T-04.2** Implement Step 2 (profile landmark detection) with the same error handling.
  > _AC-02.4 · Design §6.2 step 2_

- [ ] **T-04.3** Implement Step 3: compute the pixel-to-cm scale factor from profile nose/ankle
  landmarks and `stature_cm`.
  > _Design §6.2 step 3_

- [ ] **T-04.4** Implement Steps 4 & 5: extract half-widths (front photo) and half-depths
  (profile photo) in centimetres for bust, waist, and hips.
  > _Design §6.2 steps 4 & 5_

- [ ] **T-04.5** Implement Step 6: apply the ellipse circumference formula
  `C ≈ π × sqrt(2(a²+b²) − (a−b)²/2)` for each segment; round to `DECIMAL(5,1)`.
  Return an `EstimationResult` dataclass.
  > _AC-05.2, NFR-05 · Design §6.2 steps 6 & 7_

- [ ] **T-04.6** Add timeout guard: if the full estimate() call exceeds 30 s,
  raise `EstimationTimeoutError`.
  > _NFR-01 · Design §6.3_

---

## Phase 5 — Body Shape Classifier

- [ ] **T-05.1** Implement `BodyShapeClassifier.classify(bust, waist, hips) → str`
  applying the five rules in priority order:
  Hourglass → Pear → Inverted Triangle → Apple → Rectangle (fallback).
  > _AC-08.1, AC-08.2 · Design §7_

---

## Phase 6 — Session Service & Background Task

- [ ] **T-06.1** Implement `CaptureSessionService.create_session(user_id) → CaptureSession`
  — creates a session with `status = "empty"`, `is_active = false`.
  > _AC-01.2 · Design §8_

- [ ] **T-06.2** Implement `CaptureSessionService.upload_photo(session_id, user_id, view, file)`
  — runs the three-step validation pipeline (MIME → size → body-presence via MediaPipe),
  calls `SupabaseStorageAdapter.upload`, updates the session URL field.
  > _AC-02.1, AC-02.2, AC-02.3, AC-02.4, AC-02.5, AC-02.6 · Design §5.2_

- [ ] **T-06.3** Implement `CaptureSessionService.set_stature(session_id, user_id, stature_cm)`
  — validates range, persists `entered_stature`.
  > _AC-03.1, AC-03.2 · Design §5.3_

- [ ] **T-06.4** Implement `CaptureSessionService.trigger_processing(session_id, user_id)`
  — validates both photos + stature present, sets `status = "processing"`,
  enqueues `run_estimation` as a FastAPI `BackgroundTask`, returns `ProcessTriggerResponse`.
  Raise `HTTP 409` if status is already `processing` or `success`.
  > _AC-04.1, AC-04.2, AC-04.3 · Design §5.4 & §8_

- [ ] **T-06.5** Implement `run_estimation(session_id, db)` background task in `service.py`:
  download photos → call `estimate()` → call `classify()` → persist `RawMeasurement` →
  call `_deactivate_previous_sessions()` → set `status = "success"`, `is_active = true`.
  Catch all exceptions, set `status = "failed"` with `failure_reason`.
  > _AC-01.3, AC-05.2, AC-08.1, AC-08.2 · Design §8_

- [ ] **T-06.6** Implement `_deactivate_previous_sessions(user_id, db)` helper:
  sets `is_active = false` on all prior sessions for the user before marking the new one active.
  > _AC-01.3 · Design §3.1 (partial unique index)_

- [ ] **T-06.7** Implement retry logic in `CaptureSessionService.upload_photo`:
  when session `status == "failed"`, accept new photo upload, overwrite stored URL,
  reset `status = "empty"`, increment `retry_count`.
  > _AC-06.1, AC-06.2 · Design §5.2_

---

## Phase 7 — API Router

- [ ] **T-07.1** Implement `POST /sessions` endpoint — calls `create_session`, returns 201.
  > _AC-01.1, AC-01.2 · Design §5.1_

- [ ] **T-07.2** Implement `PUT /sessions/{session_id}/photos/{view}` endpoint —
  validates `view` in `{"front", "profile"}`, calls `upload_photo`, returns 200.
  > _AC-02.1 – AC-02.6 · Design §5.2_

- [ ] **T-07.3** Implement `PATCH /sessions/{session_id}/stature` endpoint —
  calls `set_stature`, returns 200.
  > _AC-03.1, AC-03.2 · Design §5.3_

- [ ] **T-07.4** Implement `POST /sessions/{session_id}/process` endpoint —
  calls `trigger_processing`, registers background task, returns 202.
  > _AC-04.1 – AC-04.3 · Design §5.4_

- [ ] **T-07.5** Implement `GET /sessions/{session_id}/status` endpoint —
  queries session + optional raw_measurements join, returns `SessionStatusResponse`.
  Includes `measurements` sub-object when `success`; includes `failure_reason`
  and `retry_allowed = true` when `failed`.
  > _AC-05.1, AC-05.2, AC-05.3 · Design §5.5_

- [ ] **T-07.6** Implement `GET /sessions` endpoint —
  returns caller's sessions ordered `created_at DESC`, each item includes `is_active`.
  > _AC-07.1, AC-07.2 · Design §5.6_

---

## Phase 8 — Auth & Dependency Injection

- [ ] **T-08.1** Implement `get_current_user` FastAPI dependency in `dependencies.py`:
  decode Bearer JWT (via Supabase / python-jose), return `user_id: UUID`.
  Return HTTP 401 if token is missing or invalid.
  > _AC-01.1, NFR-03_

- [ ] **T-08.2** Implement `get_session_or_404` dependency: fetch session by ID,
  verify `session.user_id == current_user.id`, raise 403 if ownership mismatch,
  raise 404 if not found.
  > _AC-02.6 · Design §5_

---

## Phase 9 — Integration & Smoke Testing

- [ ] **T-09.1** Manual smoke test (Postman / curl):
  - Create session → upload both photos → set stature → trigger process →
    poll status until `success` → verify `bust_cm`, `waist_cm`, `hips_cm`,
    `silhouette_code` are present.
  > _AC-04.2, AC-05.1, AC-05.2_

- [ ] **T-09.2** Smoke test failure path:
  - Upload a photo with no human body → verify session goes to `failed` →
    upload valid replacement photo → verify session resets to `empty` →
    retry full flow to `success`.
  > _AC-02.4, AC-06.1, AC-06.2_

- [ ] **T-09.3** Verify cross-user isolation:
  - Authenticate as User A, attempt GET/PUT on User B's session →
    verify HTTP 403 is returned.
  > _NFR-04_

- [ ] **T-09.4** Verify `is_active` flag behaviour:
  - Complete two sessions for the same user → verify only the latest has `is_active = true`.
  > _AC-01.3, AC-07.2_

---

## Phase 10 — Documentation

- [ ] **T-10.1** Update `backend/app/modules/measurements/README.md` with:
  - module purpose, endpoint table, environment variables required
    (`SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_STORAGE_BUCKET`).

- [ ] **T-10.2** Confirm inter-module contracts are documented in `design.md §12`
  and communicated to the Module 5 and Module 6 owners.
  > _Design §12_
