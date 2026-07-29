"""
Service layer for the Fabric Catalog (Module 3) and Pattern Catalog (Module 4).

Contains all business-logic guards that sit above the pure CRUD layer:

    list_available_fabrics  — wraps crud.list_available_fabrics with a 404
                              guard when a category_id filter is provided but
                              the category does not exist (Req 1 AC6).

    get_alternatives        — returns up to 3 available fabrics in the same
                              category, excluding the given fabric itself,
                              ordered by fabric_name ASC (Req 3 AC2, AC5).

    select_fabric           — enforces fabric-status rules for the selection
                              endpoint (Req 3 AC1–4).

    delete_category         — prevents deletion of a category that still owns
                              fabrics (Req 4 AC6–7).

    validate_fabrics_from_module3 — validates a list of fabric_ids against
                              Module 3's CRUD layer (same process); raises
                              FabricNotFoundError or FabricNotAvailableError
                              (Req 5 AC1–3, AC8).

    init_model              — full workflow for POST /models/init: validates
                              image, uploads to Supabase Storage, calls AI
                              analyzer, maps critical zones, computes sequential
                              name, and inserts MODEL + MODEL_CRITICAL_ZONE rows
                              in a single transaction (Req 1 AC1–8).

All functions that detect a business-rule violation raise ``HTTPException``
or a custom domain exception directly; route handlers need no additional
error-handling logic.
"""

import os
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth_catalogues import crud, ai_client, storage
from app.modules.auth_catalogues.ai_client import AILowConfidenceError, AIUnavailableError
from app.modules.auth_catalogues.storage import StorageUploadError
from app.modules.auth_catalogues.models import CriticalZone, Fabric, Model
from app.modules.auth_catalogues.schemas import (
    FabricItem,
    ModelInitResponse,
    SelectionResponse,
    ZoneItem,
)


# ---------------------------------------------------------------------------
# Module 4 — Custom domain exceptions for fabric validation
# ---------------------------------------------------------------------------


class FabricNotFoundError(Exception):
    """Raised when a fabric_id supplied for model assignment does not exist in Module 3.

    Implements: Req 5 AC2.
    """

    def __init__(self, fabric_id: UUID) -> None:
        self.fabric_id = fabric_id
        super().__init__(f"Fabric '{fabric_id}' not found in Module 3.")


class FabricNotAvailableError(Exception):
    """Raised when a fabric_id exists in Module 3 but has fabric_status != 'available'.

    Implements: Req 5 AC3.
    """

    def __init__(self, fabric_id: UUID) -> None:
        self.fabric_id = fabric_id
        super().__init__(
            f"Fabric '{fabric_id}' exists in Module 3 but is not available."
        )


# ---------------------------------------------------------------------------
# Module 4 — Completeness gate exceptions
# ---------------------------------------------------------------------------


class MissingZonesError(Exception):
    """Raised by completeness_gate when the model has zero MODEL_CRITICAL_ZONE entries
    but at least one MODEL_FABRIC entry.

    Implements: Req 6 AC2; Req 7 AC4.
    """

    def __init__(self) -> None:
        super().__init__(
            "At least one critical zone is required before publishing."
        )


class MissingFabricsError(Exception):
    """Raised by completeness_gate when the model has zero MODEL_FABRIC entries
    but at least one MODEL_CRITICAL_ZONE entry.

    Implements: Req 6 AC3; Req 7 AC4.
    """

    def __init__(self) -> None:
        super().__init__(
            "At least one compatible fabric is required before publishing."
        )


class MissingZonesAndFabricsError(Exception):
    """Raised by completeness_gate when the model has both zero MODEL_CRITICAL_ZONE
    entries and zero MODEL_FABRIC entries.

    Implements: Req 6 AC4; Req 7 AC4.
    """

    def __init__(self) -> None:
        super().__init__(
            "At least one critical zone and one compatible fabric are required before publishing."
        )


# ---------------------------------------------------------------------------
# Fabric listing
# ---------------------------------------------------------------------------


async def list_available_fabrics(
    db: AsyncSession, category_id: UUID | None = None
) -> list[Fabric]:
    """Return available fabrics, optionally filtered by *category_id*.

    If *category_id* is provided, the category is validated to exist first.
    Raises HTTP 404 if it does not (Req 1 AC6).

    Returns fabrics with ``category`` eagerly loaded so callers can access
    ``fabric.category.category_name``.
    """
    if category_id is not None:
        category = await crud.get_category(db, category_id)
        if category is None:
            raise HTTPException(
                status_code=404,
                detail=f"Category '{category_id}' not found.",
            )

    return await crud.list_available_fabrics(db, category_id=category_id)


# ---------------------------------------------------------------------------
# Fabric selection
# ---------------------------------------------------------------------------


async def get_alternatives(db: AsyncSession, fabric: Fabric) -> list[Fabric]:
    """Return up to 3 available fabrics in the same category, excluding *fabric*.

    Results are ordered by ``fabric_name`` ascending (Req 3 AC2, AC5).
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    stmt = (
        select(Fabric)
        .options(selectinload(Fabric.category))
        .where(
            Fabric.category_id == fabric.category_id,
            Fabric.fabric_status == "available",
            Fabric.fabric_id != fabric.fabric_id,
        )
        .order_by(Fabric.fabric_name)
        .limit(3)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def select_fabric(db: AsyncSession, fabric_id: UUID) -> SelectionResponse:
    """Validate and confirm a fabric selection for a client order.

    Business rules (Req 3 AC1–4):
    - Fabric does not exist  → HTTP 404
    - ``fabric_status = archived``  → HTTP 404  (treat as non-existent)
    - ``fabric_status = unavailable``  → HTTP 409 with up to 3 alternatives
    - ``fabric_status = available``  → return ``SelectionResponse``

    Raises:
        HTTPException 404: fabric not found or archived.
        HTTPException 409: fabric unavailable; response body contains
            ``{"detail": ..., "alternatives": [...]}``.
    """
    fabric = await crud.get_fabric(db, fabric_id)

    # 404 — does not exist or archived (both treated as non-existent for clients)
    if fabric is None or fabric.fabric_status == "archived":
        raise HTTPException(status_code=404, detail="Fabric not found.")

    # 409 — unavailable: return alternatives from the same category
    if fabric.fabric_status == "unavailable":
        alternatives = await get_alternatives(db, fabric)
        # Build list of FabricSummary-compatible dicts; route handler will
        # serialise them via the SelectionConflict schema.
        alternatives_data = [
            {
                "fabric_id": alt.fabric_id,
                "fabric_name": alt.fabric_name,
                "fabric_unit_price": float(alt.fabric_unit_price),
                "fabric_photo": alt.fabric_photo,
                "fabric_status": alt.fabric_status,
                "category_name": alt.category.category_name,
            }
            for alt in alternatives
        ]
        raise HTTPException(
            status_code=409,
            detail={
                "detail": "The selected fabric is currently unavailable.",
                "alternatives": alternatives_data,
            },
        )

    # HTTP 200 — fabric is available; return selection confirmation
    return SelectionResponse(
        fabric_id=fabric.fabric_id,
        fabric_elasticity_rate=float(fabric.fabric_elasticity_rate),
        reference_rigidity_level=fabric.category.reference_rigidity_level,
    )


# ---------------------------------------------------------------------------
# Category deletion guard
# ---------------------------------------------------------------------------


async def delete_category(db: AsyncSession, category_id: UUID) -> bool:
    """Delete a category only if it has no associated fabrics.

    Returns ``True`` on successful deletion, ``False`` if the category was
    not found.

    Raises:
        HTTPException 409: the category still owns one or more fabrics
            (Req 4 AC6–7).
    """
    count = await crud.count_fabrics_in_category(db, category_id)
    if count > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot delete category: {count} fabric(s) are still "
                "associated with it. Remove or reassign them first."
            ),
        )

    return await crud.delete_category(db, category_id)


# ---------------------------------------------------------------------------
# Module 4 — Fabric validation against Module 3
# ---------------------------------------------------------------------------


async def validate_fabrics_from_module3(
    db: AsyncSession,
    fabric_ids: list[UUID],
) -> None:
    """Validate that every fabric_id exists in Module 3 and is available.

    Since Module 3 and Module 4 share the same FastAPI process (both live in
    ``auth_catalogues``), this is a direct Python call to ``crud.get_fabric``
    rather than an HTTP round-trip (design §7).

    Steps:
    1. Deduplicate the input list while preserving insertion order (Req 5 AC8).
    2. For each unique fabric_id, fetch the Fabric row via Module 3 CRUD.
    3. If the row does not exist → raise ``FabricNotFoundError`` (Req 5 AC2).
    4. If the row exists but ``fabric_status != 'available'`` → raise
       ``FabricNotAvailableError`` (Req 5 AC3).
    5. If all IDs pass, return ``None`` — the caller may proceed with DB writes.

    Args:
        db:         Async SQLAlchemy session shared with the calling request.
        fabric_ids: Raw (possibly duplicate) list of fabric UUIDs from the
                    request body.

    Raises:
        FabricNotFoundError:     First fabric_id that is absent from Module 3.
        FabricNotAvailableError: First fabric_id whose fabric_status is not
                                 'available' (e.g. 'unavailable' or 'archived').

    Implements: Req 5 AC1–3, AC8; design §7.
    """
    # Deduplicate while preserving order (dict preserves insertion order in Python 3.7+).
    unique_ids: list[UUID] = list(dict.fromkeys(fabric_ids))

    for fabric_id in unique_ids:
        fabric: Fabric | None = await crud.get_fabric(db, fabric_id)

        if fabric is None:
            raise FabricNotFoundError(fabric_id)

        if fabric.fabric_status != "available":
            raise FabricNotAvailableError(fabric_id)


# ---------------------------------------------------------------------------
# Module 4 — Completeness gate
# ---------------------------------------------------------------------------


async def completeness_gate(db: AsyncSession, model_id: UUID) -> None:
    """Verify a model meets the publication completeness requirements.

    Checks that the model has at least one MODEL_CRITICAL_ZONE entry and at
    least one MODEL_FABRIC entry.  Raises the appropriate exception when
    either or both counts are zero so the caller can map it to HTTP 422.

    Decision table:
        zones == 0 AND fabrics == 0  → raise MissingZonesAndFabricsError
        zones == 0 AND fabrics  > 0  → raise MissingZonesError
        zones  > 0 AND fabrics == 0  → raise MissingFabricsError
        zones  > 0 AND fabrics  > 0  → return None  (gate passes)

    Args:
        db:       Async SQLAlchemy session.
        model_id: UUID of the model being published.

    Raises:
        MissingZonesError:           Only zones are missing (Req 6 AC2).
        MissingFabricsError:         Only fabrics are missing (Req 6 AC3).
        MissingZonesAndFabricsError: Both zones and fabrics are missing (Req 6 AC4).

    Implements: Req 6 AC2–4, AC8; Req 7 AC4; design §4.
    """
    zone_count: int = await crud.count_zones(db, model_id)
    fabric_count: int = await crud.count_fabrics(db, model_id)

    if zone_count == 0 and fabric_count == 0:
        raise MissingZonesAndFabricsError()

    if zone_count == 0:
        raise MissingZonesError()

    if fabric_count == 0:
        raise MissingFabricsError()

    # Both counts > 0 — gate passes, return None implicitly.


# ---------------------------------------------------------------------------
# Module 4 — Model initialisation  (Req 1 AC1–8)
# ---------------------------------------------------------------------------

# Allowed MIME types for inspiration images (Req 1 AC5)
_ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "image/webp"}
)

# Allowed file-name extensions — lower-cased for comparison (Req 1 AC5)
_ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".webp"})

# Maximum file size: 10 MB (Req 1 AC6)
_MAX_IMAGE_BYTES: int = 10 * 1024 * 1024


async def init_model(
    db: AsyncSession,
    image_bytes: bytes,
    filename: str,
    content_type: str,
    creator_id: str,
) -> ModelInitResponse:
    """Full workflow for the POST /models/init endpoint.

    Steps (design §5):
    1. Validate image format (content_type + filename extension) and size.
    2. Upload to Supabase Storage.
    3. Call AI Analyzer; clean up uploaded image on any AI failure.
    4. Map AI critical_zones to zone_id values (case-insensitive, silently drop
       unrecognised names).
    5. Compute sequential model_name: ``[garment_type] #[N]`` where
       N = count of existing models with same garment_type + 1.
    6. Insert MODEL row + MODEL_CRITICAL_ZONE rows in a single transaction.
    7. Return ``ModelInitResponse`` (Draft profile).

    Args:
        db:           Async SQLAlchemy session.
        image_bytes:  Raw bytes of the uploaded image.
        filename:     Original filename (e.g. ``"photo.jpg"``).
        content_type: MIME type declared by the client (e.g. ``"image/jpeg"``).
        creator_id:   UUID string of the authenticated user (from JWT).

    Returns:
        ``ModelInitResponse`` with the newly created Draft model.

    Raises:
        HTTPException 422: invalid format/size (AC5–6) or low AI confidence (AC2).
        HTTPException 500: Supabase Storage upload failure (AC7).
        HTTPException 503: AI service unreachable (AC3).

    Implements: Req 1 AC1–8; design §5.
    """
    # ── Step 1: Validate image format ────────────────────────────────────────
    # Check MIME type
    if content_type.lower() not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported image format '{content_type}'. "
                "Accepted types: JPEG, PNG, WebP."
            ),
        )

    # Check file extension (case-insensitive)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported file extension '{ext}'. "
                "Accepted extensions: .jpg, .jpeg, .png, .webp."
            ),
        )

    # ── Step 1b: Validate file size ───────────────────────────────────────────
    if len(image_bytes) > _MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"File size {len(image_bytes):,} bytes exceeds the 10 MB limit."
            ),
        )

    # ── Step 2: Upload to Supabase Storage ────────────────────────────────────
    try:
        photo_url: str = storage.upload_inspiration_image(image_bytes, filename)
    except StorageUploadError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Image upload failed: {exc}",
        ) from exc

    # ── Step 3: AI analysis (with cleanup on failure) ─────────────────────────
    try:
        ai_result = ai_client.analyze_image(image_bytes)
    except AILowConfidenceError as exc:
        storage.delete_image(photo_url)
        raise HTTPException(
            status_code=422,
            detail=(
                f"The submitted image was not recognised with sufficient confidence "
                f"({exc.confidence:.0%}). Please submit a clearer garment image."
            ),
        ) from exc
    except AIUnavailableError as exc:
        storage.delete_image(photo_url)
        raise HTTPException(
            status_code=503,
            detail="The AI analysis service is currently unavailable. Please try again later.",
        ) from exc
    except Exception as exc:  # pragma: no cover — safety net
        storage.delete_image(photo_url)
        raise HTTPException(
            status_code=503,
            detail=f"Unexpected AI analysis error: {exc}",
        ) from exc

    # ── Step 4: Map AI critical_zones → zone_id values ───────────────────────
    # Fetch all critical_zone rows from the seed table.
    zones_result = await db.execute(select(CriticalZone))
    all_zones: list[CriticalZone] = list(zones_result.scalars().all())

    # Build a case-insensitive lookup: lower(zone_name) → CriticalZone
    zone_lookup: dict[str, CriticalZone] = {
        z.zone_name.lower(): z for z in all_zones
    }

    matched_zone_ids: list[UUID] = []
    for zone_name in ai_result.critical_zones:
        zone = zone_lookup.get(zone_name.lower())
        if zone is not None:
            matched_zone_ids.append(zone.zone_id)
        # Unrecognised names are silently dropped (design §5)

    # ── Step 5: Compute sequential model_name ────────────────────────────────
    garment_type_val: str = ai_result.garment_type

    count_result = await db.execute(
        select(func.count()).where(Model.garment_type == garment_type_val)
    )
    existing_count: int = count_result.scalar_one()
    n = existing_count + 1
    model_name = f"{garment_type_val} #{n}"

    # ── Step 6: Insert MODEL + MODEL_CRITICAL_ZONE in one transaction ─────────
    model_data = {
        "model_name": model_name,
        "garment_type": garment_type_val,
        "cut_type": ai_result.cut_type,
        "photo_url": photo_url,
        "status": "Draft",
        "version": 1,
        "creator_id": UUID(creator_id),
        "zone_ids": matched_zone_ids,
    }

    new_model: Model = await crud.create_model(db, model_data)

    # ── Step 7: Build and return the response ─────────────────────────────────
    garment_enum_val = (
        new_model.garment_type.value
        if hasattr(new_model.garment_type, "value")
        else new_model.garment_type
    )
    cut_enum_val = (
        new_model.cut_type.value
        if hasattr(new_model.cut_type, "value")
        else new_model.cut_type
    )
    status_enum_val = (
        new_model.status.value
        if hasattr(new_model.status, "value")
        else new_model.status
    )

    # Resolve fabric names via JOIN (a fresh Draft has none, but be consistent)
    fabrics_raw = await crud.get_fabrics_for_model(db, new_model.model_id)

    return ModelInitResponse(
        model_id=new_model.model_id,
        model_name=new_model.model_name,
        garment_type=garment_enum_val,
        cut_type=cut_enum_val,
        status=status_enum_val,
        version=new_model.version,
        photo_url=new_model.photo_url,
        zones=[
            ZoneItem(zone_id=z.zone_id, zone_name=z.zone_name)
            for z in new_model.zones
        ],
        fabrics=[
            FabricItem(fabric_id=f["fabric_id"], fabric_name=f["fabric_name"])
            for f in fabrics_raw
        ],
    )


# ---------------------------------------------------------------------------
# Module 4 — Model editing  (Req 4 AC1–8; Req 7 AC1–2, AC5–6, AC8)
# ---------------------------------------------------------------------------


def _get_status_string(model: Model) -> str:
    """Return the model status as a plain string regardless of enum vs string storage."""
    s = model.status
    return s.value if hasattr(s, "value") else s


def _validate_update_fields(update_data: "ModelUpdateRequest") -> dict:
    """Validate and collect only the fields explicitly set in the update request.

    Returns a dict of field → value pairs ready to pass to ``crud.update_model``.

    Raises:
        HTTPException 422: if any provided field value fails validation.

    Implements: Req 4 AC2–5; Req 7 AC5.
    """
    from app.modules.auth_catalogues.schemas import (
        CutTypeEnum as SchemaCutTypeEnum,
        GarmentTypeEnum as SchemaGarmentTypeEnum,
        ModelUpdateRequest,
    )

    fields: dict = {}

    # model_name — already validated by Pydantic field_validator in the schema,
    # but we double-check here in case the service is called without going through
    # the router (e.g. tests calling the service directly with raw dicts).
    if update_data.model_name is not None:
        trimmed = update_data.model_name.strip()
        if len(trimmed) == 0:
            raise HTTPException(
                status_code=422,
                detail="model_name must not be empty or whitespace-only.",
            )
        if len(trimmed) > 100:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"model_name must not exceed 100 characters after trimming "
                    f"(got {len(trimmed)})."
                ),
            )
        fields["model_name"] = trimmed

    # description — max 1 000 chars (Req 4 AC2)
    if update_data.description is not None:
        if len(update_data.description) > 1000:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"description must not exceed 1 000 characters "
                    f"(got {len(update_data.description)})."
                ),
            )
        fields["description"] = update_data.description

    # garment_type — validated by Pydantic (GarmentTypeEnum); propagate value
    if update_data.garment_type is not None:
        # Value is already a GarmentTypeEnum instance (Pydantic validated it)
        fields["garment_type"] = update_data.garment_type

    # cut_type — validated by Pydantic (CutTypeEnum); propagate value
    if update_data.cut_type is not None:
        fields["cut_type"] = update_data.cut_type

    return fields


async def edit_model(
    db: AsyncSession,
    model_id: UUID,
    update_data: "ModelUpdateRequest",
) -> Model:
    """Status-aware dispatch for PATCH /models/{model_id}.

    Behaviour:
    - Model not found → HTTP 404 (Req 4 AC6)
    - status = Archived → HTTP 409 (Req 4 AC7)
    - status = Draft → validate fields, update in-place, return updated model
      (Req 4 AC1–5)
    - status = Published → open transaction, call create_snapshot(), apply updates,
      commit; on snapshot failure rollback and raise HTTP 500
      (Req 7 AC1–2, AC5–6, AC8)

    Args:
        db:          Async SQLAlchemy session.
        model_id:    UUID of the model to edit.
        update_data: Partial update payload (ModelUpdateRequest).

    Returns:
        Updated Model ORM instance.

    Raises:
        HTTPException 404: model does not exist.
        HTTPException 409: model is Archived (or wrong-status catch-all).
        HTTPException 422: field validation failure.
        HTTPException 500: snapshot write failure on Published model path.

    Implements: Req 4 AC1–8; Req 7 AC1–2, AC5–6, AC8; P4.1–4, P7.1, P7.4.
    """
    # ── 1. Load model — 404 if not found ─────────────────────────────────────
    model = await crud.get_model(db, model_id)
    if model is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model_id}' not found.",
        )

    status_str = _get_status_string(model)

    # ── 2. Archived guard — 409 ───────────────────────────────────────────────
    if status_str == "Archived":
        raise HTTPException(
            status_code=409,
            detail="Cannot edit an Archived model.",
        )

    # ── 3. Validate fields (common to both Draft and Published paths) ─────────
    fields = _validate_update_fields(update_data)

    # ── 4. Draft path — edit in-place, no snapshot ───────────────────────────
    if status_str == "Draft":
        if not fields:
            # Nothing to update — return current model unchanged
            return model

        updated = await crud.update_model(db, model_id, fields)
        if updated is None:
            # Should not happen (we already confirmed the model exists above)
            raise HTTPException(
                status_code=404,
                detail=f"Model '{model_id}' not found.",
            )
        return updated

    # ── 5. Published path — snapshot + update in a single transaction ─────────
    if status_str == "Published":
        try:
            # create_snapshot() flushes but does NOT commit — it relies on the
            # caller to commit (or rollback) the surrounding transaction.
            await crud.create_snapshot(db, model)
        except Exception as exc:
            # Snapshot write failed — rollback the session to keep the DB clean.
            await db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Snapshot creation failed; all changes have been rolled back: {exc}",
            ) from exc

        if not fields:
            # No field updates requested — still needed to persist the snapshot.
            await db.commit()
            return await crud.get_model(db, model_id)

        # Apply field updates to the live MODEL row and commit both snapshot + update.
        for field, value in fields.items():
            if hasattr(value, "value"):
                value = value.value
            setattr(model, field, value)

        await db.commit()
        # Re-fetch to return a fully refreshed instance with eager-loaded relations.
        return await crud.get_model(db, model_id)

    # ── 6. Unexpected status — safety fallback ────────────────────────────────
    raise HTTPException(
        status_code=409,
        detail=f"Model has an unexpected status '{status_str}' and cannot be edited.",
    )


# ---------------------------------------------------------------------------
# Module 4 — Zone assignment  (Req 4 AC9–11; P4.4)
# ---------------------------------------------------------------------------


async def assign_zones(
    db: AsyncSession,
    model_id: UUID,
    zone_ids: list[UUID],
) -> list[CriticalZone]:
    """Validate and atomically replace critical zone assignments for a model.

    Validation rules (executed before any DB write):
    - Model must exist (404 if not).
    - Every zone_id in the input list must exist in the CRITICAL_ZONE reference
      table (422 on first unknown zone_id; Req 4 AC10; P4.4).
    - An empty zone_ids list is accepted and clears all assignments (Req 4 AC11).

    After validation, calls crud.set_zones() which deletes existing entries and
    inserts the new set atomically (Req 4 AC9).

    Args:
        db:       Async SQLAlchemy session.
        model_id: UUID of the model whose zones are being updated.
        zone_ids: New list of zone UUIDs (may be empty to clear all zones).

    Returns:
        List of CriticalZone ORM instances currently assigned to the model
        after the update.

    Raises:
        HTTPException 404: Model does not exist.
        HTTPException 422: One or more zone_ids do not exist in CRITICAL_ZONE.

    Implements: Req 4 AC9–11; P4.4.
    """
    # ── 1. Load model — 404 if not found ─────────────────────────────────────
    model = await crud.get_model(db, model_id)
    if model is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model_id}' not found.",
        )

    # ── 2. Validate each zone_id against the CRITICAL_ZONE reference table ────
    # Perform all validation BEFORE any DB write so the operation is all-or-nothing.
    for zone_id in zone_ids:
        result = await db.execute(
            select(CriticalZone).where(CriticalZone.zone_id == zone_id)
        )
        zone = result.scalar_one_or_none()
        if zone is None:
            raise HTTPException(
                status_code=422,
                detail=f"Zone '{zone_id}' does not exist in the critical_zone catalog.",
            )

    # ── 3. Atomically replace zone assignments ────────────────────────────────
    # crud.set_zones() handles the delete-all-then-insert logic (Req 4 AC9).
    # An empty zone_ids list clears all assignments (Req 4 AC11).
    await crud.set_zones(db, model_id, zone_ids)

    # ── 4. Return the updated zone list ──────────────────────────────────────
    return await crud.get_zones_for_model(db, model_id)


# ---------------------------------------------------------------------------
# Module 4 — Fabric assignment  (Req 5 AC1–8; P5.1, P5.2, P5.3)
# ---------------------------------------------------------------------------


async def assign_fabrics(
    db: AsyncSession,
    model_id: UUID,
    fabric_ids: list[UUID],
) -> list[dict]:
    """Validate and atomically replace fabric assignments for a model.

    Validation rules (executed before any DB write):
    - Model must exist (404 if not; Req 5 AC6).
    - Input list is deduplicated before any further processing (Req 5 AC8).
    - For a non-empty list, every unique fabric_id must exist in Module 3 and
      have ``fabric_status = available`` (422 on first failure; Req 5 AC2–3).
    - An empty fabric_ids list is accepted and clears all assignments (Req 5 AC4).
    - Published models: fabric reassignment applies the same validation and
      updates MODEL_FABRIC entries WITHOUT incrementing version or creating a
      snapshot — that only happens on explicit ``POST /publish`` (Req 5 AC7).

    After validation, calls ``crud.set_fabrics()`` which deletes existing entries
    and inserts the new set atomically (Req 5 AC1).

    Args:
        db:         Async SQLAlchemy session.
        model_id:   UUID of the model whose fabrics are being updated.
        fabric_ids: New list of fabric UUIDs (may contain duplicates; may be
                    empty to clear all fabric assignments).

    Returns:
        List of ``{fabric_id, fabric_name}`` dicts currently assigned to the
        model after the update.

    Raises:
        HTTPException 404: Model does not exist (Req 5 AC6).
        HTTPException 422: A fabric_id is unknown or unavailable in Module 3
            (Req 5 AC2–3; raised by ``validate_fabrics_from_module3``).

    Implements: Req 5 AC1–8; P5.1, P5.2, P5.3.
    """
    # ── 1. Load model — 404 if not found ─────────────────────────────────────
    model = await crud.get_model(db, model_id)
    if model is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model_id}' not found.",
        )

    # ── 2. Deduplicate fabric_ids (Req 5 AC8) ─────────────────────────────────
    # dict.fromkeys preserves insertion order while removing duplicates.
    unique_ids: list[UUID] = list(dict.fromkeys(fabric_ids))

    # ── 3. Validate each unique fabric_id against Module 3 (Req 5 AC2–3) ──────
    # Only validate when the list is non-empty; an empty list simply clears all
    # fabric assignments without needing Module 3 calls (Req 5 AC4).
    if unique_ids:
        try:
            await validate_fabrics_from_module3(db, unique_ids)
        except FabricNotFoundError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "fabric_not_found",
                    "fabric_id": str(exc.fabric_id),
                },
            ) from exc
        except FabricNotAvailableError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "fabric_not_available",
                    "fabric_id": str(exc.fabric_id),
                },
            ) from exc

    # ── 4. Atomically replace fabric assignments (Req 5 AC1) ──────────────────
    # crud.set_fabrics() handles delete-all-then-insert in one transaction.
    # An empty unique_ids list clears all assignments (Req 5 AC4).
    # No snapshot, no version increment for Published models (Req 5 AC7).
    await crud.set_fabrics(db, model_id, unique_ids)

    # ── 5. Return the updated fabric list ─────────────────────────────────────
    return await crud.get_fabrics_for_model(db, model_id)


# ---------------------------------------------------------------------------
# Module 4 — Model publishing  (Req 6 AC1–8; Req 7 AC3–4)
# ---------------------------------------------------------------------------


async def publish_model(
    db: AsyncSession,
    model_id: UUID,
) -> Model:
    """Publish a Draft model or re-publish (version-bump) a Published model.

    State-machine dispatch:

    - **Draft** → run completeness gate → set ``status = Published`` → return
      updated model (Req 6 AC1–4).
    - **Published** → run completeness gate → increment ``version += 1`` →
      return updated model (Req 7 AC3–4).
    - **Archived** → raise HTTP 409 — terminal state, cannot be published
      (Req 6 AC8).
    - **Not found** → raise HTTP 404 (Req 6 AC5).

    The completeness gate (``completeness_gate()``) is called before any DB
    write and raises ``MissingZonesError``, ``MissingFabricsError``, or
    ``MissingZonesAndFabricsError`` on failure.  The caller (route handler)
    maps these to HTTP 422.

    No snapshot is created here — snapshots are created exclusively by the
    PATCH (edit) flow, not by publish (Req 7 AC9; design §4).

    Args:
        db:       Async SQLAlchemy session.
        model_id: UUID of the model to publish.

    Returns:
        Updated ``Model`` ORM instance with all relationships eager-loaded.

    Raises:
        HTTPException 404: model does not exist (Req 6 AC5).
        HTTPException 409: model is Archived (Req 6 AC8).
        MissingZonesError:           completeness gate — zones missing (Req 6 AC2; Req 7 AC4).
        MissingFabricsError:         completeness gate — fabrics missing (Req 6 AC3; Req 7 AC4).
        MissingZonesAndFabricsError: completeness gate — both missing (Req 6 AC4; Req 7 AC4).

    Implements: Req 6 AC1–5, AC8; Req 7 AC3–4; design §3 state machine.
    """
    from datetime import datetime

    # ── 1. Load model — 404 if not found ─────────────────────────────────────
    model = await crud.get_model(db, model_id)
    if model is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model_id}' not found.",
        )

    status_str = _get_status_string(model)

    # ── 2. Archived guard — 409 (terminal state) ──────────────────────────────
    if status_str == "Archived":
        raise HTTPException(
            status_code=409,
            detail="Cannot publish an Archived model.",
        )

    # ── 3. Run completeness gate (raises MissingZones/Fabrics* on failure) ────
    # Called BEFORE any DB write so that on failure no state changes are made
    # (Req 6 AC2–4; Req 7 AC4; P6.2 transition atomicity).
    await completeness_gate(db, model_id)

    # ── 4. Draft path — transition to Published ───────────────────────────────
    if status_str == "Draft":
        updated = await crud.update_model(
            db,
            model_id,
            {
                "status": "Published",
                "updated_at": datetime.utcnow(),
            },
        )
        if updated is None:  # pragma: no cover — model confirmed to exist above
            raise HTTPException(
                status_code=404,
                detail=f"Model '{model_id}' not found.",
            )
        return updated

    # ── 5. Published path — increment version (republish) ────────────────────
    # Design §3 state machine: Published + publish → version++  (Req 7 AC3).
    # No snapshot is created here; snapshots happen only on PATCH (Req 7 AC9).
    if status_str == "Published":
        updated = await crud.update_model(
            db,
            model_id,
            {
                "version": model.version + 1,
                "updated_at": datetime.utcnow(),
            },
        )
        if updated is None:  # pragma: no cover — model confirmed to exist above
            raise HTTPException(
                status_code=404,
                detail=f"Model '{model_id}' not found.",
            )
        return updated

    # ── 6. Unexpected status — safety fallback ────────────────────────────────
    raise HTTPException(
        status_code=409,
        detail=f"Model has an unexpected status '{status_str}' and cannot be published.",
    )


# ---------------------------------------------------------------------------
# Module 4 — Model archiving  (Req 8 AC1, AC5–8; P8.3)
# ---------------------------------------------------------------------------


async def archive_model(
    db: AsyncSession,
    model_id: UUID,
) -> Model:
    """Archive a Draft or Published model, transitioning its status to 'Archived'.

    State-machine rules:

    - **Draft or Published** → set ``status = Archived`` → return updated model
      (Req 8 AC1).
    - **Archived** → raise HTTP 409 — already in terminal state, no changes made
      (Req 8 AC6; P8.3 idempotency guard).
    - **Not found** → raise HTTP 404 (Req 8 AC5).
    - **DB error during write** → rollback and raise HTTP 500; status reverts to
      pre-archive value (Req 8 AC8).

    Args:
        db:       Async SQLAlchemy session.
        model_id: UUID of the model to archive.

    Returns:
        Updated ``Model`` ORM instance with all relationships eager-loaded.

    Raises:
        HTTPException 404: model does not exist (Req 8 AC5).
        HTTPException 409: model is already Archived (Req 8 AC6; P8.3).
        HTTPException 500: DB error during the status update (Req 8 AC8).

    Implements: Req 8 AC1, AC5–8; P8.3.
    """
    from datetime import datetime

    from sqlalchemy.exc import SQLAlchemyError

    # ── 1. Load model — 404 if not found ─────────────────────────────────────
    model = await crud.get_model(db, model_id)
    if model is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model_id}' not found.",
        )

    status_str = _get_status_string(model)

    # ── 2. Already-Archived guard — 409 (P8.3 idempotency guard) ─────────────
    if status_str == "Archived":
        raise HTTPException(
            status_code=409,
            detail="Model is already archived.",
        )

    # ── 3. Apply status transition inside a DB write, rollback on error ───────
    try:
        updated = await crud.update_model(
            db,
            model_id,
            {
                "status": "Archived",
                "updated_at": datetime.utcnow(),
            },
        )
    except SQLAlchemyError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Archive operation failed due to a database error.",
        ) from exc

    if updated is None:  # pragma: no cover — model confirmed to exist above
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model_id}' not found.",
        )

    return updated
