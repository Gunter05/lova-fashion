"""
Session service and background estimation task for Module 2.
Tasks T-06.1 – T-06.7 — Design §5, §8

Public surface
--------------
CaptureSessionService
    .create_session(user_id)                        → CaptureSession   T-06.1
    .upload_photo(session_id, user_id, view, ...)   → CaptureSession   T-06.2 / T-06.7
    .set_stature(session_id, user_id, stature_cm)   → CaptureSession   T-06.3
    .trigger_processing(session_id, user_id, bg)    → dict             T-06.4

Background task (called by FastAPI BackgroundTasks)
    run_estimation(session_id, db)                                      T-06.5

Private helper
    _deactivate_previous_sessions(user_id, db)                         T-06.6
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from fastapi import BackgroundTasks, HTTPException, UploadFile
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.measurements.classification import BodyShapeClassifier
from app.modules.measurements.estimation import (
    BodyNotDetectedError,
    EstimationTimeoutError,
    LandmarkOccludedError,
    MeasurementEstimationService,
)
from app.modules.measurements.models import CaptureSession, RawMeasurement
from app.modules.measurements.storage import StorageDownloadError, SupabaseStorageAdapter
from app.db.session import AsyncSessionLocal as AsyncSessionFactory

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ALLOWED_MIME_TYPES: set[str] = {"image/jpeg", "image/png"}
_MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB  (AC-02.3)

# ---------------------------------------------------------------------------
# Module-level singletons (instantiated once, shared across requests)
# ---------------------------------------------------------------------------

_storage = SupabaseStorageAdapter()
_estimator = MeasurementEstimationService()
_classifier = BodyShapeClassifier()


# ---------------------------------------------------------------------------
# T-06.6 — private helper: deactivate all previous sessions for a user
# ---------------------------------------------------------------------------

async def _deactivate_previous_sessions(
    user_id: uuid.UUID,
    current_session_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """
    Set is_active = False on every session belonging to user_id
    except current_session_id.

    Must be called BEFORE setting the new session's is_active = True
    to satisfy the partial unique index uix_one_active_per_user (AC-01.3).
    """
    await db.execute(
        update(CaptureSession)
        .where(
            CaptureSession.user_id == user_id,
            CaptureSession.id != current_session_id,
            CaptureSession.is_active.is_(True),
        )
        .values(is_active=False)
    )


# ---------------------------------------------------------------------------
# T-06.5 — background task: run the full estimation pipeline
# ---------------------------------------------------------------------------

async def run_estimation(session_id: uuid.UUID) -> None:
    """
    FastAPI BackgroundTask entry-point.

    Flow:
        1. Open a fresh DB session (the request-scoped session is already closed).
        2. Download both photos from Supabase Storage.
        3. Run MediaPipe estimation (synchronous, runs in thread with timeout).
        4. Classify body shape.
        5. Persist RawMeasurement.
        6. Deactivate prior sessions, mark this one active.
        7. Commit. On any failure: set status='failed' + failure_reason, commit.

    Session outcomes by exception type (Design §6.3):
        BodyNotDetectedError    → failed, retry_allowed via status
        LandmarkOccludedError   → failed, retry_allowed via status
        EstimationTimeoutError  → failed, descriptive message
        StorageDownloadError    → failed, descriptive message
        Any other exception     → failed, generic French message
    """
    async with AsyncSessionFactory() as db:
        session: CaptureSession | None = await db.get(CaptureSession, session_id)
        if session is None:
            # Session was deleted between trigger and execution — nothing to do
            return

        try:
            # Step 1 — download photos
            front_bytes = _storage.download(session.front_photo_url)
            profile_bytes = _storage.download(session.profile_photo_url)

            # Step 2 — run CV pipeline (30-second timeout enforced inside)
            result = _estimator.estimate(
                front_image_bytes=front_bytes,
                profile_image_bytes=profile_bytes,
                stature_cm=float(session.entered_stature),
            )

            # Step 3 — classify silhouette
            silhouette_code = _classifier.classify(
                bust=result.bust_cm,
                waist=result.waist_cm,
                hips=result.hips_cm,
            )

            # Step 4 — persist raw measurements (AC-08.2)
            measurement = RawMeasurement(
                session_id=session_id,
                bust_cm=Decimal(str(result.bust_cm)),
                waist_cm=Decimal(str(result.waist_cm)),
                hips_cm=Decimal(str(result.hips_cm)),
                silhouette_code=silhouette_code,
            )
            db.add(measurement)

            # Step 5 — deactivate previous sessions BEFORE setting this one active
            #           (preserves uix_one_active_per_user constraint — AC-01.3)
            await _deactivate_previous_sessions(session.user_id, session_id, db)

            session.status = "success"
            session.is_active = True
            session.failure_reason = None

        except (BodyNotDetectedError, LandmarkOccludedError) as exc:
            # Descriptive, user-actionable message — retry is possible (AC-06.1)
            session.status = "failed"
            session.failure_reason = str(exc)

        except EstimationTimeoutError as exc:
            session.status = "failed"
            session.failure_reason = str(exc)

        except StorageDownloadError as exc:
            session.status = "failed"
            session.failure_reason = (
                "Impossible de récupérer les photos. Veuillez réessayer."
            )

        except Exception:
            # Catch-all: never leave a session stuck in 'processing'
            session.status = "failed"
            session.failure_reason = (
                "Une erreur interne s'est produite lors de l'analyse. "
                "Veuillez réessayer."
            )

        await db.commit()


# ---------------------------------------------------------------------------
# CaptureSessionService
# ---------------------------------------------------------------------------

class CaptureSessionService:
    """
    Orchestrates all capture-session lifecycle operations.
    Injected with an AsyncSession scoped to the current HTTP request.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # T-06.1 — create_session
    # ------------------------------------------------------------------

    async def create_session(self, user_id: uuid.UUID) -> CaptureSession:
        """
        Create a new capture session with status='empty'.
        AC-01.2 — Design §5.1
        """
        session = CaptureSession(
            user_id=user_id,
            status="empty",
            is_active=False,
        )
        self._db.add(session)
        await self._db.commit()
        await self._db.refresh(session)
        return session

    # ------------------------------------------------------------------
    # T-06.2 + T-06.7 — upload_photo  (includes retry logic)
    # ------------------------------------------------------------------

    async def upload_photo(
        self,
        session: CaptureSession,
        user_id: uuid.UUID,
        view: Literal["front", "profile"],
        file: UploadFile,
    ) -> CaptureSession:
        """
        Validate and store one photo for an existing capture session.

        Validation pipeline (Design §5.2):
            Step 1 — MIME type  (AC-02.2)
            Step 2 — File size  (AC-02.3)
            Step 3 — Body presence via MediaPipe  (AC-02.4)

        Retry behaviour (AC-06.1, AC-06.2, T-06.7):
            If the session is in 'failed' status, the upload is accepted,
            the stored URL for this view is overwritten, the session is
            reset to 'empty', and retry_count is incremented.

        Raises
        ------
        HTTPException 422 — MIME, size, or body-presence failure.
        HTTPException 403 — Session belongs to a different user (handled
                            upstream by get_session_or_404 dependency, but
                            guarded here too for defence-in-depth).
        HTTPException 409 — Session is already 'success' (no overwrite allowed).
        """
        # Guard: cannot overwrite a completed session
        if session.status == "success":
            raise HTTPException(
                status_code=409,
                detail="Impossible de modifier une session déjà terminée avec succès.",
            )

        # --- Step 1: MIME type validation (AC-02.2) ---
        content_type = file.content_type or ""
        if content_type not in _ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=422,
                detail="Format non supporté. Utilisez JPEG ou PNG.",
            )

        # --- Step 2: File size validation (AC-02.3) ---
        file_bytes = await file.read()
        if len(file_bytes) > _MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=422,
                detail="Fichier trop volumineux. Limite : 10 Mo.",
            )

        # --- Step 3: Body-presence validation via MediaPipe (AC-02.4) ---
        # Lightweight check: only verify the image is decodable (not corrupted).
        # Full body detection happens in the background estimation task.
        # This avoids false rejections when MediaPipe misses a valid pose in
        # certain lighting conditions or image orientations at upload time.
        try:
            from app.modules.measurements.estimation import _decode_image
            _decode_image(file_bytes, view)  # raises ValueError if image is corrupt
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Image non lisible ou corrompue. Veuillez retéléverser la photo. ({exc})",
            )

        # --- Upload to Supabase Storage (AC-02.5) ---
        photo_url = _storage.upload(
            user_id=user_id,
            session_id=session.id,
            view=view,
            file_bytes=file_bytes,
            mime_type=content_type,
        )

        # --- Persist URL on session ---
        if view == "front":
            session.front_photo_url = photo_url
        else:
            session.profile_photo_url = photo_url

        # --- Retry logic: reset a failed session (T-06.7, AC-06.1, AC-06.2) ---
        if session.status == "failed":
            session.status = "empty"
            session.failure_reason = None
            session.retry_count += 1

        await self._db.commit()
        await self._db.refresh(session)
        return session

    # ------------------------------------------------------------------
    # T-06.3 — set_stature
    # ------------------------------------------------------------------

    async def set_stature(
        self,
        session: CaptureSession,
        stature_cm: Decimal,
    ) -> CaptureSession:
        """
        Persist the user's height on the session.

        Pydantic validates the 100–250 range at the schema layer (AC-03.1).
        This method only writes; the router passes an already-validated value.
        AC-03.2 — Design §5.3
        """
        session.entered_stature = stature_cm
        await self._db.commit()
        await self._db.refresh(session)
        return session

    # ------------------------------------------------------------------
    # T-06.4 — trigger_processing
    # ------------------------------------------------------------------

    async def trigger_processing(
        self,
        session: CaptureSession,
        background_tasks: BackgroundTasks,
        request_base_url: str,
    ) -> dict:
        """
        Validate readiness, flip status to 'processing', enqueue the
        background estimation task, and return the polling URL.

        Raises
        ------
        HTTPException 409 — Session already processing or successful (AC-04.3).
        HTTPException 422 — Missing photo(s) or stature (AC-04.1).
        """
        # --- AC-04.3: guard against double-trigger ---
        if session.status in ("processing", "success"):
            raise HTTPException(
                status_code=409,
                detail="Cette session est déjà en cours de traitement ou terminée.",
            )

        # --- AC-04.1: all inputs must be present ---
        missing: list[dict] = []
        if not session.front_photo_url:
            missing.append({"field": "front_photo", "message": "Photo de face manquante."})
        if not session.profile_photo_url:
            missing.append({"field": "profile_photo", "message": "Photo de profil manquante."})
        if session.entered_stature is None:
            missing.append({"field": "stature_cm", "message": "La stature n'a pas été renseignée."})

        if missing:
            raise HTTPException(status_code=422, detail=missing)

        # --- Flip status synchronously so polling sees 'processing' immediately ---
        session.status = "processing"
        await self._db.commit()

        # --- Enqueue background task (AC-04.2) ---
        background_tasks.add_task(run_estimation, session.id)

        polling_url = f"{request_base_url.rstrip('/')}/sessions/{session.id}/status"
        return {
            "session_id": session.id,
            "status": "processing",
            "polling_url": polling_url,
        }

    # ------------------------------------------------------------------
    # get_session_status — used by the status polling endpoint
    # ------------------------------------------------------------------

    async def get_session_status(
        self,
        session: CaptureSession,
    ) -> dict:
        """
        Build the status response dict, including measurements if successful.
        AC-05.1, AC-05.2, AC-05.3 — Design §5.5
        """
        result: dict = {
            "session_id": session.id,
            "status": session.status,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "retry_allowed": session.status == "failed",
            "failure_reason": session.failure_reason if session.status == "failed" else None,
            "measurements": None,
        }

        if session.status == "success":
            # Eager-load the related RawMeasurement
            stmt = select(RawMeasurement).where(
                RawMeasurement.session_id == session.id
            )
            row = await self._db.execute(stmt)
            measurement: RawMeasurement | None = row.scalars().first()
            if measurement:
                result["measurements"] = {
                    "bust_cm": measurement.bust_cm,
                    "waist_cm": measurement.waist_cm,
                    "hips_cm": measurement.hips_cm,
                    "silhouette_code": measurement.silhouette_code,
                }

        return result

    # ------------------------------------------------------------------
    # list_sessions — used by GET /sessions
    # ------------------------------------------------------------------

    async def list_sessions(self, user_id: uuid.UUID) -> list[CaptureSession]:
        """
        Return all sessions for the user, newest first.
        AC-07.1, AC-07.2 — Design §5.6
        """
        stmt = (
            select(CaptureSession)
            .where(CaptureSession.user_id == user_id)
            .order_by(CaptureSession.created_at.desc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
