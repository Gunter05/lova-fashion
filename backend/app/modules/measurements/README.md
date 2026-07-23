# Module 2 — Photo Capture & Measurement Estimation
# (Prise de mesure)

## Purpose

This module lets an authenticated user submit two photos (front-view and profile-view)
plus their height in centimetres and receive — without a physical tape measure — their
estimated anatomical measurements (bust, waist, hips) and body-shape classification.

Results are persisted in the database and consumed by:
- **Module 5** — Ease Allowance Calculation Engine (reads `bust_cm`, `waist_cm`, `hips_cm`)
- **Module 6** — Fabric / Pattern / Body Shape Compatibility Engine (reads `silhouette_code`)

---

## Directory layout

```
backend/app/modules/measurements/
├── __init__.py         Module package marker
├── router.py           FastAPI APIRouter — all 6 endpoints
├── service.py          CaptureSessionService + run_estimation() background task
├── estimation.py       MeasurementEstimationService — MediaPipe + ellipse geometry
├── classification.py   BodyShapeClassifier — 5-silhouette priority ruleset
├── schemas.py          Pydantic request / response models
├── models.py           SQLAlchemy ORM models (CaptureSession, RawMeasurement, BodyShape)
├── storage.py          SupabaseStorageAdapter — upload / download
└── dependencies.py     FastAPI dependencies: get_db, get_current_user, get_session_or_404
```

---

## API endpoints

All endpoints are mounted at `/api/v1/measurements` and require
`Authorization: Bearer <JWT>`.

| Method  | Path                                    | Description                          | Success | Key errors       |
|---------|-----------------------------------------|--------------------------------------|---------|------------------|
| `POST`  | `/sessions`                             | Create a new capture session         | 201     | 401              |
| `PUT`   | `/sessions/{session_id}/photos/{view}`  | Upload front or profile photo        | 200     | 401, 403, 404, 422 |
| `PATCH` | `/sessions/{session_id}/stature`        | Set user height (100–250 cm)         | 200     | 401, 403, 404, 422 |
| `POST`  | `/sessions/{session_id}/process`        | Trigger async measurement estimation | 202     | 401, 403, 404, 409, 422 |
| `GET`   | `/sessions/{session_id}/status`         | Poll status and results              | 200     | 401, 403, 404    |
| `GET`   | `/sessions`                             | List caller's sessions               | 200     | 401              |

Interactive documentation is available at `/docs` (Swagger UI) once the server is running.

---

## Session lifecycle

```
POST /sessions
      │
      ▼
   [ empty ]
      │  PUT /photos/front
      │  PUT /photos/profile
      │  PATCH /stature
      ▼
POST /sessions/{id}/process
      │
      ▼
   [ processing ]  ──────────────────────────────┐
      │                                           │
      │ (background task completes)               │ (error / timeout)
      ▼                                           ▼
   [ success ]                              [ failed ]
      │                                           │
      │  is_active = true                         │  retry_allowed = true
      │  raw_measurements written                 │  PUT new photos to reset
      ▼                                           ▼
  Module 5 & 6                              [ empty ]  (retry_count++)
  consume results
```

---

## Photo validation pipeline

Each photo upload runs three checks in order:

1. **MIME type** — must be `image/jpeg` or `image/png` → HTTP 422 if invalid
2. **File size** — must be ≤ 10 MB → HTTP 422 if exceeded
3. **Body presence** — MediaPipe Pose must detect a human body → HTTP 422 if absent

---

## Measurement estimation pipeline

Once both photos and height are present and processing is triggered:

1. MediaPipe Pose detects landmarks on the **front photo** (shoulders, hips, elbow)
2. MediaPipe Pose detects landmarks on the **profile photo** (nose, ankle, shoulder, hip)
3. Pixel-to-cm scale factor: `stature_cm ÷ |nose_y − ankle_y|` in pixels
4. Half-widths extracted from front photo (shoulder span → bust, hip span → hips,
   interpolated at elbow level → waist)
5. Half-depths estimated from profile photo using anthropometric depth ratios
6. Ellipse circumference per segment:
   `C ≈ π × [3(a+b) − √((3a+b)(a+3b))]` (Ramanujan approximation)
7. Results rounded to `DECIMAL(5,1)` and persisted in `raw_measurements`

Hard timeout: **30 seconds**. Exceeded jobs set session to `failed` with `retry_allowed`.

---

## Body shape classification

After estimation, measurements are passed to `BodyShapeClassifier.classify()`.
Rules are evaluated in strict priority order:

| Priority | Code                | Condition |
|----------|---------------------|-----------|
| 1        | `HOURGLASS`         | `waist/bust ≤ 0.75` AND `waist/hips ≤ 0.75` AND `\|bust−hips\| ≤ 5 cm` |
| 2        | `PEAR`              | `hips > bust + 5 cm` AND `waist < hips` |
| 3        | `INVERTED_TRIANGLE` | `bust > hips + 5 cm` |
| 4        | `APPLE`             | `waist ≥ bust` OR `waist ≥ hips` |
| 5        | `RECTANGLE`         | fallback (none of the above) |

---

## Database tables

| Table               | Purpose                                              |
|---------------------|------------------------------------------------------|
| `capture_sessions`  | One row per capture attempt; owns the session state  |
| `raw_measurements`  | One row per successful session; stores the estimates |
| `body_shapes`       | Reference table; seeded with the 5 silhouette codes  |

All tables have Row Level Security enabled — users can only access their own data.
Migration SQL files are in `backend/migrations/` (run in order 001 → 004).

---

## Environment variables

Add these to `backend/.env` (see `.env.example` for the full template):

| Variable                  | Required | Description |
|---------------------------|----------|-------------|
| `DATABASE_URL`            | Yes      | PostgreSQL connection string (psycopg2 format) |
| `SUPABASE_URL`            | Yes      | Supabase project URL (`https://<id>.supabase.co`) |
| `SUPABASE_KEY`            | Yes      | Supabase anon or service-role key |
| `SUPABASE_JWT_SECRET`     | Yes      | JWT secret — Supabase dashboard → Project Settings → API → JWT Secret |
| `SUPABASE_STORAGE_BUCKET` | No       | Storage bucket name (default: `captures`) |

---

## Running the server

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The server will be available at `http://localhost:8000`.
Health check: `GET /health` → `{"status": "ok"}`

---

## Smoke tests

See `docs/modules/module2_smoke_tests.md` for a step-by-step curl-based test guide
covering the happy path, failure/retry path, cross-user isolation, and `is_active` behaviour.

---

## Inter-module contracts

See `docs/modules/module2_smoke_tests.md` and `.kiro/specs/prise-de-mesure/design.md §12`
for the exact JSON contracts published to Module 5 and Module 6.

Downstream modules query `raw_measurements` directly via the shared Supabase database:

```sql
-- Active measurement profile for a given user
SELECT rm.*
FROM raw_measurements rm
JOIN capture_sessions cs ON cs.id = rm.session_id
WHERE cs.user_id = '<user_id>'
  AND cs.is_active = true;
```

---

## Spec reference

| Artefact | Path |
|---|---|
| Requirements | `.kiro/specs/prise-de-mesure/requirements.md` |
| Design | `.kiro/specs/prise-de-mesure/design.md` |
| Tasks | `.kiro/specs/prise-de-mesure/tasks.md` |
| Functional doc | `docs/modules/module2_photo_capture_and_measurement.md` |
| Data model | `docs/data-models/module_2_capture_session_measurement.md` |
| Smoke tests | `docs/modules/module2_smoke_tests.md` |
