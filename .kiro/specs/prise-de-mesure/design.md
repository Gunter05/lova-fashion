# Design — Module 2: Photo Capture & Measurement Estimation
# (Prise de mesure — Architecture technique)

## 1. Module Position in the System

```
┌──────────────────────────────────────────────────────────────────┐
│                        CLIENT (Frontend)                         │
└──────────────────────────┬───────────────────────────────────────┘
                           │ HTTPS / JWT
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│               FastAPI  ─  backend/app/modules/measurements/      │
│                                                                  │
│   router.py          ← HTTP routing, input validation            │
│   service.py         ← Orchestration & business logic            │
│   estimation.py      ← MeasurementEstimationService (CV + math)  │
│   schemas.py         ← Pydantic request / response models        │
│   models.py          ← SQLAlchemy ORM models                     │
│   storage.py         ← Supabase Storage adapter                  │
└──────────────────────────┬───────────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
     PostgreSQL (Supabase)      Supabase Storage
     capture_sessions           captures/{user_id}/{session_id}/
     raw_measurements           front.jpg | profile.jpg
     body_shapes (ref table)
```

Upstream dependency: Module 1 issues the JWT consumed by this module's auth middleware.  
Downstream consumers: Module 5 reads `raw_measurements`; Module 6 reads `silhouette_code`.

---

## 2. Directory Layout

```
backend/app/modules/measurements/
├── __init__.py
├── router.py          # FastAPI APIRouter, all /sessions endpoints
├── service.py         # CaptureSessionService — orchestrates upload, trigger, retry
├── estimation.py      # MeasurementEstimationService — MediaPipe + ellipse calculations
├── classification.py  # BodyShapeClassifier — applies ratio ruleset
├── schemas.py         # Pydantic I/O schemas
├── models.py          # SQLAlchemy models (CaptureSession, RawMeasurement)
├── storage.py         # SupabaseStorageAdapter
└── dependencies.py    # FastAPI dependency injectors (get_current_user, get_session_or_404)
```

---

## 3. Database Schema

### 3.1 Table: `capture_sessions`

```sql
CREATE TABLE capture_sessions (
    id                UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID          NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    status            VARCHAR(20)   NOT NULL DEFAULT 'empty'
                                    CHECK (status IN ('empty','processing','success','failed')),
    front_photo_url   TEXT,
    profile_photo_url TEXT,
    entered_stature   DECIMAL(5,1)  CHECK (entered_stature BETWEEN 100 AND 250),
    is_active         BOOLEAN       NOT NULL DEFAULT false,
    retry_count       INTEGER       NOT NULL DEFAULT 0,
    failure_reason    TEXT,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- Keep updated_at current automatically
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

CREATE TRIGGER trg_capture_sessions_updated_at
BEFORE UPDATE ON capture_sessions
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Only one active session per user at a time (partial unique index)
CREATE UNIQUE INDEX uix_one_active_per_user
ON capture_sessions (user_id)
WHERE is_active = true;

-- RLS: users see only their own sessions
ALTER TABLE capture_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY sessions_owner ON capture_sessions
    USING (user_id = auth.uid());
```

### 3.2 Table: `raw_measurements`

```sql
CREATE TABLE raw_measurements (
    id             UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id     UUID          NOT NULL UNIQUE REFERENCES capture_sessions(id) ON DELETE CASCADE,
    bust_cm        DECIMAL(5,1)  NOT NULL,
    waist_cm       DECIMAL(5,1)  NOT NULL,
    hips_cm        DECIMAL(5,1)  NOT NULL,
    silhouette_code VARCHAR(30)  NOT NULL REFERENCES body_shapes(code),
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT now()
);

ALTER TABLE raw_measurements ENABLE ROW LEVEL SECURITY;
CREATE POLICY measurements_owner ON raw_measurements
    USING (
        session_id IN (
            SELECT id FROM capture_sessions WHERE user_id = auth.uid()
        )
    );
```

### 3.3 Table: `body_shapes` (reference / seed data)

```sql
CREATE TABLE body_shapes (
    code        VARCHAR(30)  PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    description TEXT
);

INSERT INTO body_shapes (code, name, description) VALUES
  ('HOURGLASS',          'Sablier (X)',           'Waist/Bust ≤ 0.75 AND Waist/Hips ≤ 0.75 AND |Bust−Hips| ≤ 5 cm'),
  ('PEAR',               'Poire (A)',              'Hips > Bust + 5 cm AND Waist < Hips'),
  ('INVERTED_TRIANGLE',  'Triangle inversé (V)',   'Bust > Hips + 5 cm'),
  ('APPLE',              'Pomme (O)',              'Waist ≥ Bust OR Waist ≥ Hips'),
  ('RECTANGLE',          'Rectangle (H)',          'None of the above');
```

---

## 4. Pydantic Schemas (`schemas.py`)

```python
# Request / Response contracts

class SessionCreateResponse(BaseModel):
    session_id: UUID
    status: str           # "empty"
    created_at: datetime

class StatureUpdateRequest(BaseModel):
    stature_cm: Decimal = Field(..., ge=100, le=250)

class ProcessTriggerResponse(BaseModel):
    session_id: UUID
    status: str           # "processing"
    polling_url: str

class SessionStatusResponse(BaseModel):
    session_id: UUID
    status: str
    created_at: datetime
    updated_at: datetime
    retry_allowed: bool   # true only when status == "failed"
    failure_reason: str | None = None
    # included only when status == "success":
    measurements: MeasurementResult | None = None

class MeasurementResult(BaseModel):
    bust_cm:        Decimal
    waist_cm:       Decimal
    hips_cm:        Decimal
    silhouette_code: str

class SessionListItem(BaseModel):
    session_id: UUID
    status:     str
    is_active:  bool
    created_at: datetime
```

---

## 5. API Endpoints

Base path: `/api/v1/measurements`  
All endpoints require `Authorization: Bearer <JWT>`.

| Method | Path | Description | Success | Errors |
|---|---|---|---|---|
| `POST` | `/sessions` | Create a new capture session | 201 | 401 |
| `PUT` | `/sessions/{session_id}/photos/{view}` | Upload one photo (`view` = `front` \| `profile`) | 200 | 401, 403, 404, 422 |
| `PATCH` | `/sessions/{session_id}/stature` | Set or update the stature | 200 | 401, 403, 404, 422 |
| `POST` | `/sessions/{session_id}/process` | Trigger async estimation | 202 | 401, 403, 404, 409, 422 |
| `GET` | `/sessions/{session_id}/status` | Poll estimation status + results | 200 | 401, 403, 404 |
| `GET` | `/sessions` | List all sessions for the caller | 200 | 401 |

### 5.1 POST `/sessions`

No request body. Returns `SessionCreateResponse`.

### 5.2 PUT `/sessions/{session_id}/photos/{view}`

- Request: `multipart/form-data` with field `file` (binary).
- `view` path param must be `front` or `profile`; else HTTP 422.
- Validation pipeline (in order):
  1. MIME type check (`image/jpeg` | `image/png`)
  2. File size check (≤ 10 MB)
  3. MediaPipe body-presence check
- On success: stores to Supabase Storage, updates session URL field, returns updated session object (200).

### 5.3 PATCH `/sessions/{session_id}/stature`

- Request body: `{"stature_cm": 172.0}`
- Returns updated session object (200).

### 5.4 POST `/sessions/{session_id}/process`

- Validates session has both photo URLs and a valid stature.
- Sets `status = "processing"` synchronously (DB write).
- Enqueues `run_estimation(session_id)` as a FastAPI `BackgroundTask`.
- Returns `ProcessTriggerResponse` (202) immediately.

### 5.5 GET `/sessions/{session_id}/status`

- Returns `SessionStatusResponse`.
- When `status == "success"`: populates `measurements` sub-object from `raw_measurements`.
- When `status == "failed"`: populates `failure_reason` and sets `retry_allowed = true`.

### 5.6 GET `/sessions`

- Returns list of `SessionListItem`, ordered by `created_at DESC`.
- Filtered to calling user's sessions via RLS (no server-side filter needed beyond auth).

---

## 6. Computer Vision Pipeline (`estimation.py`)

### 6.1 Interface

```python
class MeasurementEstimationService:
    def estimate(
        self,
        front_image_bytes: bytes,
        profile_image_bytes: bytes,
        stature_cm: float,
    ) -> EstimationResult:
        ...

@dataclass
class EstimationResult:
    bust_cm:  float
    waist_cm: float
    hips_cm:  float
```

### 6.2 Processing Steps

```
1. LANDMARK DETECTION (front photo)
   ├── Load image bytes → NumPy array via OpenCV
   ├── Feed to mediapipe.solutions.pose (static_image_mode=True)
   ├── Extract normalised landmarks:
   │     LEFT_SHOULDER (11), RIGHT_SHOULDER (12)  → shoulder width
   │     LEFT_HIP (23),      RIGHT_HIP (24)        → hip width
   │     LEFT_ELBOW (13) y-coord                   → approximate waist level
   └── If pose.results.pose_landmarks is None → raise BodyNotDetectedError

2. LANDMARK DETECTION (profile photo)
   ├── Same pipeline; extract:
   │     NOSE (0) y-coord        → head top proxy
   │     LEFT_ANKLE (27) y-coord → foot proxy
   │     Torso depth markers (LEFT_SHOULDER, LEFT_HIP)
   └── If pose.results.pose_landmarks is None → raise BodyNotDetectedError

3. PIXEL-TO-CM SCALE FACTOR
   ├── pixel_height = |nose_y_px − ankle_y_px|  (profile photo)
   └── scale = stature_cm / pixel_height          [cm per pixel]

4. HALF-WIDTH EXTRACTION (front photo, converted to cm)
   ├── bust_half_width_cm  = (right_shoulder_x − left_shoulder_x) × scale / 2
   ├── hip_half_width_cm   = (right_hip_x − left_hip_x) × scale / 2
   └── waist_half_width_cm = estimated at mid-point between shoulder & hip landmarks

5. HALF-DEPTH EXTRACTION (profile photo, converted to cm)
   ├── bust_half_depth_cm   = shoulder depth span × scale / 2
   └── hip_half_depth_cm    = hip depth span × scale / 2
       waist_half_depth_cm  = interpolated at same relative y-level

6. ELLIPSE CIRCUMFERENCE FORMULA
   For each body segment (bust, waist, hips):
     C ≈ π × sqrt( 2 × (a² + b²) − (a−b)²/2 )
   where a = half-width and b = half-depth of the ellipse cross-section.

7. ROUNDING
   All results rounded to 1 decimal place (DECIMAL(5,1)).
```

### 6.3 Error Conditions

| Exception | Cause | Session outcome |
|---|---|---|
| `BodyNotDetectedError` | No pose landmarks found in a photo | `failed` + descriptive `failure_reason` |
| `LandmarkOccludedError` | Required landmark confidence < 0.5 | `failed` + descriptive `failure_reason` |
| `StorageDownloadError` | Cannot fetch photo from Supabase Storage | `failed` + retry allowed |
| `EstimationTimeoutError` | Processing exceeds 30 s | `failed` + retry allowed |

---

## 7. Body Shape Classifier (`classification.py`)

```python
class BodyShapeClassifier:
    def classify(self, bust: float, waist: float, hips: float) -> str:
        """Returns one of the five silhouette codes."""

        # Priority 1 — Hourglass
        if (waist / bust <= 0.75
                and waist / hips <= 0.75
                and abs(bust - hips) <= 5):
            return "HOURGLASS"

        # Priority 2 — Pear
        if hips > bust + 5 and waist < hips:
            return "PEAR"

        # Priority 3 — Inverted Triangle
        if bust > hips + 5:
            return "INVERTED_TRIANGLE"

        # Priority 4 — Apple
        if waist >= bust or waist >= hips:
            return "APPLE"

        # Priority 5 — Rectangle (fallback)
        return "RECTANGLE"
```

---

## 8. Async Estimation Background Task (`service.py`)

```python
async def run_estimation(session_id: UUID, db: AsyncSession):
    """
    Called by FastAPI BackgroundTasks after POST /process.
    Fetches photo bytes → runs estimation → persists results or failure.
    """
    session = await db.get(CaptureSession, session_id)
    try:
        front_bytes   = await storage.download(session.front_photo_url)
        profile_bytes = await storage.download(session.profile_photo_url)

        result = estimation_service.estimate(
            front_bytes, profile_bytes, float(session.entered_stature)
        )
        silhouette = classifier.classify(result.bust_cm, result.waist_cm, result.hips_cm)

        # Persist raw measurements
        measurement = RawMeasurement(
            session_id=session_id,
            bust_cm=result.bust_cm,
            waist_cm=result.waist_cm,
            hips_cm=result.hips_cm,
            silhouette_code=silhouette,
        )
        db.add(measurement)

        # Mark session successful and set as active
        await _deactivate_previous_sessions(session.user_id, db)
        session.status    = "success"
        session.is_active = True

    except (BodyNotDetectedError, LandmarkOccludedError) as e:
        session.status         = "failed"
        session.failure_reason = str(e)
    except Exception as e:
        session.status         = "failed"
        session.failure_reason = "Erreur interne. Veuillez réessayer."

    await db.commit()
```

---

## 9. Supabase Storage Layout

```
Bucket: captures  (private, RLS enforced)

captures/
└── {user_id}/
    └── {session_id}/
        ├── front.jpg
        └── profile.jpg
```

RLS policy on the bucket: `auth.uid()::text = (storage.foldername(name))[1]`  
This ensures users can only read/write paths that start with their own `user_id`.

---

## 10. Error Response Envelope

All HTTP errors return:

```json
{
  "detail": "<human-readable message in French>"
}
```

For 422 validation errors with multiple fields, FastAPI's default structure is extended:

```json
{
  "detail": [
    {"field": "stature_cm", "message": "La stature doit être comprise entre 100 cm et 250 cm."},
    {"field": "front_photo", "message": "Fichier manquant."}
  ]
}
```

---

## 11. Key Dependencies (`requirements.txt` additions)

| Package | Version | Purpose |
|---|---|---|
| `mediapipe` | `0.10.14` | Pose landmark detection |
| `opencv-python-headless` | `4.10.0.84` | Image decoding (no GUI deps) |
| `numpy` | `1.26.4` | Array maths for pixel calculations |
| `python-multipart` | `0.0.9` | FastAPI multipart/form-data upload support |
| `supabase` | `2.9.1` | Supabase Python client (DB + Storage) |

---

## 12. Inter-Module Contracts

### Output to Module 5 (Ease Allowance Engine)

```json
{
  "session_id": "<uuid>",
  "user_id":    "<uuid>",
  "bust_cm":    87.5,
  "waist_cm":   68.0,
  "hips_cm":    93.0
}
```

### Output to Module 6 (Compatibility Engine)

```json
{
  "session_id":     "<uuid>",
  "user_id":        "<uuid>",
  "silhouette_code": "HOURGLASS"
}
```

Both modules query `raw_measurements` directly via the shared Supabase database, joining on `session_id` where `capture_sessions.is_active = true` for the relevant `user_id`.

### Canonical SQL query for downstream modules

```sql
-- Retrieve the active measurement profile for a given user.
-- Replace :user_id with the UUID of the authenticated user.
SELECT
    cs.user_id,
    cs.id          AS session_id,
    rm.bust_cm,
    rm.waist_cm,
    rm.hips_cm,
    rm.silhouette_code,
    rm.created_at  AS measured_at
FROM raw_measurements rm
JOIN capture_sessions cs ON cs.id = rm.session_id
WHERE cs.user_id   = :user_id
  AND cs.is_active = true
LIMIT 1;
```

### Availability guarantee

This query returns a row only when a user has at least one successful capture session.
Downstream modules (5 and 6) must handle the case where no row exists (user has not yet
completed a capture session) by returning an appropriate `HTTP 424 Failed Dependency`
or equivalent error to the frontend.

### Table ownership

Module 2 is the **sole writer** of `capture_sessions` and `raw_measurements`.
Modules 5 and 6 are **read-only** consumers — they must never INSERT or UPDATE
these tables directly.
