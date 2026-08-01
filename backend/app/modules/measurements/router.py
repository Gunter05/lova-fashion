"""
API router for Module 2 — Photo Capture & Measurement Estimation.
Tasks T-07.1 – T-07.6 — Design §5

Mounted at /api/v1/measurements (registered in main.py).
All endpoints require a valid Bearer JWT (enforced by get_current_user).

Endpoints
---------
POST   /sessions                              Create capture session           201
PUT    /sessions/{session_id}/photos/{view}   Upload front or profile photo    200
PATCH  /sessions/{session_id}/stature         Set user stature                 200
POST   /sessions/{session_id}/process         Trigger async estimation         202
GET    /sessions/{session_id}/status          Poll status + results            200
GET    /sessions                              List caller's sessions           200
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.measurements.dependencies import (
    get_current_user,
    get_db,
    get_session_or_404,
)
from app.modules.measurements.models import CaptureSession
from app.modules.measurements.schemas import (
    PhotoUploadResponse,
    ProcessTriggerResponse,
    SessionCreateResponse,
    SessionListItem,
    SessionListResponse,
    SessionStatusResponse,
    StatureUpdateRequest,
    StatureUpdateResponse,
    MeasurementResult,
)
from app.modules.measurements.service import CaptureSessionService

router = APIRouter()


# ---------------------------------------------------------------------------
# T-07.1 — POST /sessions
# Create a new capture session (AC-01.1, AC-01.2)
# ---------------------------------------------------------------------------

@router.post(
    "/sessions",
    response_model=SessionCreateResponse,
    status_code=201,
    summary="Créer une nouvelle session de capture",
    description=(
        "Initialise une session de capture avec le statut `empty`. "
        "Nécessite un token Bearer valide."
    ),
)
async def create_session(
    current_user: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionCreateResponse:
    """
    AC-01.1 — 401 if no valid JWT.
    AC-01.2 — Session created with status='empty'; returns session_id + created_at.
    """
    svc = CaptureSessionService(db)
    session = await svc.create_session(user_id=current_user)
    return SessionCreateResponse(
        session_id=session.id,
        status="empty",
        created_at=session.created_at,
    )


# ---------------------------------------------------------------------------
# T-07.2 — PUT /sessions/{session_id}/photos/{view}
# Upload front or profile photo (AC-02.1 – AC-02.6)
# ---------------------------------------------------------------------------

@router.put(
    "/sessions/{session_id}/photos/{view}",
    response_model=PhotoUploadResponse,
    status_code=200,
    summary="Téléverser une photo (face ou profil)",
    description=(
        "Téléverse une photo JPEG ou PNG (max 10 Mo) pour la vue spécifiée. "
        "La photo est validée (MIME, taille, présence du corps via MediaPipe) "
        "avant d'être stockée dans Supabase Storage."
    ),
)
async def upload_photo(
    session_id: uuid.UUID,
    view: Literal["front", "profile"],
    file: UploadFile = File(..., description="Photo JPEG ou PNG, max 10 Mo."),
    current_user: uuid.UUID = Depends(get_current_user),
    session: CaptureSession = Depends(get_session_or_404),
    db: AsyncSession = Depends(get_db),
) -> PhotoUploadResponse:
    """
    AC-02.1 — Accepts each photo individually; session ready for processing
              only when both are present.
    AC-02.2 — 422 for non JPEG/PNG MIME type.
    AC-02.3 — 422 for file > 10 MB.
    AC-02.4 — 422 if MediaPipe detects no human body.
    AC-02.5 — Photo stored at captures/{user_id}/{session_id}/{view}.jpg.
    AC-02.6 — 403/404 enforced by get_session_or_404; 409 for success sessions.
    AC-06.1 — Failed sessions accept new photos (retry reset handled in service).
    """
    svc = CaptureSessionService(db)
    updated = await svc.upload_photo(
        session=session,
        user_id=current_user,
        view=view,
        file=file,
    )
    photo_url = (
        updated.front_photo_url if view == "front" else updated.profile_photo_url
    )
    return PhotoUploadResponse(
        session_id=updated.id,
        view=view,
        photo_url=photo_url or "",
        status=updated.status,
    )


# ---------------------------------------------------------------------------
# T-07.3 — PATCH /sessions/{session_id}/stature
# Set or update the user's stature (AC-03.1, AC-03.2)
# ---------------------------------------------------------------------------

@router.patch(
    "/sessions/{session_id}/stature",
    response_model=StatureUpdateResponse,
    status_code=200,
    summary="Renseigner la stature (taille en cm)",
    description=(
        "Enregistre la taille de l'utilisateur en centimètres (100–250). "
        "Peut être appelé avant ou après le téléversement des photos."
    ),
)
async def set_stature(
    session_id: uuid.UUID,
    body: StatureUpdateRequest,
    current_user: uuid.UUID = Depends(get_current_user),
    session: CaptureSession = Depends(get_session_or_404),
    db: AsyncSession = Depends(get_db),
) -> StatureUpdateResponse:
    """
    AC-03.1 — Pydantic enforces 100 ≤ stature_cm ≤ 250; returns 422 otherwise.
    AC-03.2 — Persists entered_stature; returns updated session object.
    """
    svc = CaptureSessionService(db)
    updated = await svc.set_stature(session=session, stature_cm=body.stature_cm)
    return StatureUpdateResponse(
        session_id=updated.id,
        entered_stature=updated.entered_stature,
        status=updated.status,
    )


# ---------------------------------------------------------------------------
# T-07.4 — POST /sessions/{session_id}/process
# Trigger async measurement estimation (AC-04.1 – AC-04.3)
# ---------------------------------------------------------------------------

@router.post(
    "/sessions/{session_id}/process",
    response_model=ProcessTriggerResponse,
    status_code=202,
    summary="Lancer l'estimation des mesures",
    description=(
        "Valide que les deux photos et la stature sont présentes, "
        "passe la session en statut `processing`, et lance l'analyse "
        "MediaPipe en tâche de fond. Retourne une URL de polling."
    ),
)
async def trigger_processing(
    session_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: uuid.UUID = Depends(get_current_user),
    session: CaptureSession = Depends(get_session_or_404),
    db: AsyncSession = Depends(get_db),
) -> ProcessTriggerResponse:
    """
    AC-04.1 — 422 with field-level list if any input is missing.
    AC-04.2 — Returns HTTP 202 with polling_url immediately; task runs in background.
    AC-04.3 — 409 if session is already 'processing' or 'success'.
    """
    svc = CaptureSessionService(db)
    # Build base URL from the incoming request so the polling URL is always
    # correct regardless of the deployment domain.
    base_url = str(request.base_url).rstrip("/") + "/api/v1/measurements"
    result = await svc.trigger_processing(
        session=session,
        background_tasks=background_tasks,
        request_base_url=base_url,
    )
    return ProcessTriggerResponse(
        session_id=result["session_id"],
        status="processing",
        polling_url=result["polling_url"],
    )


# ---------------------------------------------------------------------------
# T-07.5 — GET /sessions/{session_id}/status
# Poll estimation status + results (AC-05.1 – AC-05.3)
# ---------------------------------------------------------------------------

@router.get(
    "/sessions/{session_id}/status",
    response_model=SessionStatusResponse,
    status_code=200,
    summary="Consulter le statut d'une session",
    description=(
        "Retourne le statut de la session (`empty`, `processing`, `success`, `failed`). "
        "Inclut les mesures estimées quand le statut est `success`, "
        "et le motif d'échec avec `retry_allowed=true` quand il est `failed`."
    ),
)
async def get_session_status(
    session_id: uuid.UUID,
    current_user: uuid.UUID = Depends(get_current_user),
    session: CaptureSession = Depends(get_session_or_404),
    db: AsyncSession = Depends(get_db),
) -> SessionStatusResponse:
    """
    AC-05.1 — Returns session_id, status, created_at, updated_at.
    AC-05.2 — Includes measurements sub-object when status == 'success'.
    AC-05.3 — Includes failure_reason and retry_allowed=True when status == 'failed'.
    """
    svc = CaptureSessionService(db)
    data = await svc.get_session_status(session=session)

    # Build the optional measurements sub-object
    measurements: MeasurementResult | None = None
    if data["measurements"] is not None:
        measurements = MeasurementResult(**data["measurements"])

    return SessionStatusResponse(
        session_id=data["session_id"],
        status=data["status"],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        retry_allowed=data["retry_allowed"],
        failure_reason=data["failure_reason"],
        measurements=measurements,
        front_photo_url=session.front_photo_url,
        profile_photo_url=session.profile_photo_url,
    )


# ---------------------------------------------------------------------------
# T-07.6 — GET /sessions
# List all sessions for the authenticated user (AC-07.1, AC-07.2)
# ---------------------------------------------------------------------------

@router.get(
    "/sessions",
    response_model=SessionListResponse,
    status_code=200,
    summary="Lister toutes les sessions de l'utilisateur",
    description=(
        "Retourne l'historique des sessions de capture de l'utilisateur, "
        "triées par date décroissante. Le champ `is_active` identifie "
        "la session de mesures courante."
    ),
)
async def list_sessions(
    current_user: uuid.UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionListResponse:
    """
    AC-07.1 — Only the caller's sessions are returned (RLS + service filter).
    AC-07.2 — Each item includes is_active boolean.
    """
    svc = CaptureSessionService(db)
    sessions = await svc.list_sessions(user_id=current_user)
    items = [
        SessionListItem(
            session_id=s.id,
            status=s.status,
            is_active=s.is_active,
            created_at=s.created_at,
        )
        for s in sessions
    ]
    return SessionListResponse(sessions=items, total=len(items))
