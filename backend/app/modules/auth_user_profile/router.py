"""
API router for the Fabric Catalog (Module 3) and Pattern Catalog (Module 4).

All routes are mounted here and registered in ``backend/main.py`` with the
``/api/v1`` prefix.

Module 3 coverage:
    T6  — Category endpoints  (GET/POST/PATCH/DELETE /categories)
    T7  — Client fabric endpoints  (GET /fabrics, GET /fabrics/{id}, POST /fabrics/{id}/select)
    T8  — Manager fabric endpoints (POST/PATCH/DELETE /fabrics)
    T9  — Photo upload             (POST /fabrics/{id}/photo)
    T10 — Internal properties      (GET /fabrics/{id}/properties)

Module 4 coverage (Task 16):
    POST   /models/init                      — Req 1 AC1–8
    GET    /models                           — Req 2 AC1–7
    GET    /models/{model_id}                — Req 3 AC1–6
    PATCH  /models/{model_id}                — Req 4 AC1–8; Req 7 AC1–6
    PUT    /models/{model_id}/zones          — Req 4 AC9–11
    PUT    /models/{model_id}/fabrics        — Req 5 AC1–8
    POST   /models/{model_id}/publish        — Req 6 AC1–8; Req 7 AC3–4
    POST   /models/{model_id}/archive        — Req 8 AC1, AC5–8
    GET    /models/{model_id}/constraints    — Req 9 AC1–7
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Header, Query, Response, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth_catalogues import crud, service
from app.modules.auth_catalogues.dependencies import (
    get_current_role,
    require_role,
    require_client,
    require_admin,
    require_authenticated,
)
from app.modules.auth_catalogues.schemas import (
    ArchiveOut,
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    ConstraintsOut,
    FabricAssignmentRequest,
    FabricCreate,
    FabricDetail,
    FabricItem,
    FabricProperties,
    FabricStatus,
    FabricSummary,
    FabricUpdate,
    GarmentTypeEnum,
    ModelDetailOut,
    ModelInitResponse,
    ModelListItem,
    ModelListOut,
    ModelUpdateRequest,
    SelectionResponse,
    ZoneAssignmentRequest,
    ZoneItem,
)
from app.modules.auth_catalogues import storage
from app.modules.auth_catalogues.storage import StorageUploadError
from app.modules.auth_catalogues.service import (
    MissingFabricsError,
    MissingZonesError,
    MissingZonesAndFabricsError,
)

router = APIRouter(tags=["Fabric Categories"])


# ---------------------------------------------------------------------------
# Category routes — Req 4 AC1–8
# ---------------------------------------------------------------------------


@router.get(
    "/categories",
    response_model=list[CategoryResponse],
    summary="List all fabric categories",
)
async def list_categories(
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(get_current_role),
) -> list[CategoryResponse]:
    """Return all fabric categories in alphabetical order.

    Accessible to any authenticated role (client or catalog_manager).
    Implements Req 4 AC1 (read access).
    """
    categories = await crud.list_categories(db)
    return categories  # type: ignore[return-value]


@router.get(
    "/categories/{category_id}",
    response_model=CategoryResponse,
    summary="Get a single fabric category",
)
async def get_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(get_current_role),
) -> CategoryResponse:
    """Return the fabric category with the given *category_id*.

    Accessible to any authenticated role.
    Returns HTTP 404 if the category does not exist.
    Implements Req 4 AC1 (read access).
    """
    category = await crud.get_category(db, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category '{category_id}' not found.",
        )
    return category  # type: ignore[return-value]


@router.post(
    "/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a fabric category",
)
async def create_category(
    data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_role("catalog_manager")),
) -> CategoryResponse:
    """Create a new fabric category.

    Requires the ``catalog_manager`` role (HTTP 403 otherwise).
    Returns HTTP 201 with the newly created category, including its generated
    ``category_id``.
    Implements Req 4 AC1–3, AC8.
    """
    category = await crud.create_category(db, data)
    return category  # type: ignore[return-value]


@router.patch(
    "/categories/{category_id}",
    response_model=CategoryResponse,
    summary="Partially update a fabric category",
)
async def update_category(
    category_id: UUID,
    data: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_role("catalog_manager")),
) -> CategoryResponse:
    """Apply a partial update to the fabric category with the given *category_id*.

    Only the fields present in the request body are applied; omitted fields
    remain unchanged.
    Requires the ``catalog_manager`` role (HTTP 403 otherwise).
    Returns HTTP 404 if the category does not exist.
    Implements Req 4 AC4–5, AC8.
    """
    category = await crud.update_category(db, category_id, data)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category '{category_id}' not found.",
        )
    return category  # type: ignore[return-value]


@router.delete(
    "/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a fabric category",
)
async def delete_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_role("catalog_manager")),
) -> Response:
    """Permanently delete the fabric category with the given *category_id*.

    Requires the ``catalog_manager`` role (HTTP 403 otherwise).
    Returns HTTP 409 if the category still has associated fabrics.
    Returns HTTP 404 if the category does not exist.
    Returns HTTP 204 (No Content) on success.
    Implements Req 4 AC6–8.
    """
    # service.delete_category raises 409 if fabrics still reference this category
    deleted = await service.delete_category(db, category_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category '{category_id}' not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Client fabric routes — T7
# Req 1 AC1–6, Req 2 AC1–4, Req 3 AC1–6
# ---------------------------------------------------------------------------


@router.get(
    "/fabrics",
    response_model=list[FabricSummary],
    summary="List available fabrics",
)
async def list_fabrics(
    category_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_role("client")),
) -> list[FabricSummary]:
    """Return all fabrics with ``fabric_status = available``.

    Accepts an optional ``?category_id=`` query parameter to filter by category.
    Raises HTTP 404 if the specified category does not exist (Req 1 AC6).
    Excludes ``unavailable`` and ``archived`` fabrics (Req 1 AC3).
    Implements Req 1 AC1–6.
    """
    fabrics = await service.list_available_fabrics(db, category_id=category_id)
    return [
        FabricSummary(
            fabric_id=f.fabric_id,
            fabric_name=f.fabric_name,
            fabric_unit_price=float(f.fabric_unit_price),
            fabric_photo=f.fabric_photo,
            fabric_status=f.fabric_status,
            category_name=f.category.category_name,
        )
        for f in fabrics
    ]


@router.get(
    "/fabrics/{fabric_id}",
    response_model=FabricDetail,
    summary="Get fabric detail",
)
async def get_fabric(
    fabric_id: UUID,
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_role("client")),
) -> FabricDetail:
    """Return the full detail of a fabric by its ``fabric_id``.

    - Returns HTTP 404 if the fabric does not exist (Req 2 AC2).
    - Returns HTTP 404 if ``fabric_status = archived`` (Req 2 AC3).
    - Returns HTTP 200 with full detail for ``unavailable`` fabrics (Req 2 AC4).
    - Returns HTTP 200 with full detail for ``available`` fabrics (Req 2 AC1).
    Implements Req 2 AC1–4.
    """
    fabric = await crud.get_fabric(db, fabric_id)

    if fabric is None or fabric.fabric_status == "archived":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fabric not found.",
        )

    return FabricDetail(
        fabric_id=fabric.fabric_id,
        fabric_name=fabric.fabric_name,
        fabric_unit_price=float(fabric.fabric_unit_price),
        fabric_photo=fabric.fabric_photo,
        fabric_status=fabric.fabric_status,
        category_name=fabric.category.category_name,
        fabric_elasticity_rate=float(fabric.fabric_elasticity_rate),
        fabric_weight=float(fabric.fabric_weight),
        fabric_composition=fabric.fabric_composition,
        category_id=fabric.category_id,
        reference_rigidity_level=fabric.category.reference_rigidity_level,
    )


@router.post(
    "/fabrics/{fabric_id}/select",
    response_model=SelectionResponse,
    summary="Select a fabric for an order",
)
async def select_fabric(
    fabric_id: UUID,
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_role("client")),
) -> SelectionResponse:
    """Confirm a fabric selection for an order.

    - Returns HTTP 200 ``SelectionResponse`` when fabric is ``available`` (Req 3 AC1).
    - Returns HTTP 409 ``SelectionConflict`` when fabric is ``unavailable``,
      including up to 3 alternative fabrics sorted by name (Req 3 AC2, AC5).
    - Returns HTTP 404 when fabric is ``archived`` or does not exist (Req 3 AC3–4).
    Implements Req 3 AC1–6.
    """
    try:
        return await service.select_fabric(db, fabric_id)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_409_CONFLICT:
            # service.select_fabric raises 409 with detail={detail: ..., alternatives: [...]}
            # Re-raise as a proper JSONResponse so the body matches SelectionConflict schema.
            # UUID objects must be serialised to strings before passing to JSONResponse.
            import json as _json

            def _default(obj):
                if hasattr(obj, "__str__") and type(obj).__name__ == "UUID":
                    return str(obj)
                raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

            content_str = _json.dumps(exc.detail, default=_default)
            content = _json.loads(content_str)
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=content,
            )
        raise


# ---------------------------------------------------------------------------
# Manager / internal fabric routes — T8
# Req 5 AC1–12
# ---------------------------------------------------------------------------


def _fabric_detail(fabric) -> FabricDetail:
    """Build a FabricDetail response from an ORM Fabric instance.

    Requires ``fabric.category`` to be eagerly loaded (which all CRUD write
    functions guarantee via ``get_fabric`` + ``selectinload``).
    """
    return FabricDetail(
        fabric_id=fabric.fabric_id,
        fabric_name=fabric.fabric_name,
        fabric_unit_price=float(fabric.fabric_unit_price),
        fabric_photo=fabric.fabric_photo,
        fabric_status=fabric.fabric_status,
        category_name=fabric.category.category_name,
        fabric_elasticity_rate=float(fabric.fabric_elasticity_rate),
        fabric_weight=float(fabric.fabric_weight),
        fabric_composition=fabric.fabric_composition,
        category_id=fabric.category_id,
        reference_rigidity_level=fabric.category.reference_rigidity_level,
    )


@router.post(
    "/fabrics",
    response_model=FabricDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Create a fabric reference",
)
async def create_fabric(
    data: FabricCreate,
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_role("catalog_manager")),
) -> FabricDetail:
    """Create a new fabric reference in the catalog.

    Requires the ``catalog_manager`` role (HTTP 403 otherwise).
    Validates that the supplied ``category_id`` references an existing
    category; returns HTTP 422 if it does not (Req 5 AC3).
    The new fabric defaults to ``fabric_status = available`` (Req 5 AC1).
    Returns HTTP 201 with the full ``FabricDetail`` on success.
    Implements Req 5 AC1–6, AC12.
    """
    category = await crud.get_category(db, data.category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Category '{data.category_id}' does not exist.",
        )

    fabric = await crud.create_fabric(db, data)
    return _fabric_detail(fabric)


@router.patch(
    "/fabrics/{fabric_id}",
    response_model=FabricDetail,
    summary="Partially update a fabric reference",
)
async def update_fabric(
    fabric_id: UUID,
    data: FabricUpdate,
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_role("catalog_manager")),
) -> FabricDetail:
    """Apply a partial update to an existing fabric reference.

    Only the fields present in the request body are applied; omitted fields
    remain unchanged.
    Requires the ``catalog_manager`` role (HTTP 403 otherwise).
    If ``category_id`` is provided, validates it references an existing
    category; returns HTTP 422 if it does not (Req 5 AC7).
    Returns HTTP 404 if the fabric does not exist (Req 5 AC8).
    Implements Req 5 AC7–12.
    """
    if data.category_id is not None:
        category = await crud.get_category(db, data.category_id)
        if category is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Category '{data.category_id}' does not exist.",
            )

    fabric = await crud.update_fabric(db, fabric_id, data)
    if fabric is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fabric not found.",
        )
    return _fabric_detail(fabric)


@router.delete(
    "/fabrics/{fabric_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete (archive) a fabric reference",
)
async def delete_fabric(
    fabric_id: UUID,
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_role("catalog_manager")),
) -> Response:
    """Soft-delete a fabric by setting its status to ``archived``.

    The fabric row is **not** physically removed; it is excluded from all
    client-facing responses but remains in the database for historical
    reference (Req 5 AC10).
    Requires the ``catalog_manager`` role (HTTP 403 otherwise).
    Returns HTTP 404 if the fabric does not exist.
    Returns HTTP 204 (No Content) on success.
    Implements Req 5 AC10, AC12.
    """
    fabric = await crud.update_fabric(
        db, fabric_id, FabricUpdate(fabric_status=FabricStatus.archived)
    )
    if fabric is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fabric not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Photo upload route — T9
# Req 6 AC1–5
# ---------------------------------------------------------------------------


@router.post(
    "/fabrics/{fabric_id}/photo",
    response_model=FabricDetail,
    summary="Upload or replace a fabric photo",
)
async def upload_fabric_photo(
    fabric_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_role("catalog_manager")),
) -> FabricDetail:
    """Upload (or replace) the photo for a fabric reference.

    Accepts a ``multipart/form-data`` request with a single ``file`` field.

    - Returns HTTP 404 if the fabric does not exist (Req 6 AC2).
    - Returns HTTP 500 if the Supabase Storage upload fails; ``fabric_photo``
      is NOT updated in this case (Req 6 AC3, P6.1 atomicity).
    - On success, updates ``fabric_photo`` with the public URL returned by
      Supabase Storage and returns the full updated ``FabricDetail`` (Req 6
      AC1).  Replaces any previously stored URL (Req 6 AC5).
    - Requires the ``catalog_manager`` role (HTTP 403 otherwise — Req 6 AC4).

    Implements Req 6 AC1–5.
    """
    # Req 6 AC2 — 404 if fabric does not exist
    fabric = await crud.get_fabric(db, fabric_id)
    if fabric is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fabric not found.",
        )

    # Read uploaded bytes
    file_bytes: bytes = await file.read()
    content_type: str = file.content_type or "application/octet-stream"

    # Attempt Supabase Storage upload — Req 6 AC3 / P6.1 atomicity:
    # Do NOT update the DB if this raises StorageUploadError.
    try:
        public_url: str = await storage.upload_fabric_photo(
            fabric_id=str(fabric_id),
            file_bytes=file_bytes,
            content_type=content_type,
        )
    except StorageUploadError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Photo upload failed: {exc}",
        )

    # Upload succeeded — update fabric_photo (Req 6 AC1, AC5)
    updated_fabric = await crud.update_fabric(
        db, fabric_id, FabricUpdate(fabric_photo=public_url)
    )
    if updated_fabric is None:  # pragma: no cover — extremely unlikely race condition
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fabric not found.",
        )

    return _fabric_detail(updated_fabric)


# ---------------------------------------------------------------------------
# Internal technical properties route — T10
# Req 7 AC1–4
# ---------------------------------------------------------------------------


@router.get(
    "/fabrics/{fabric_id}/properties",
    response_model=FabricProperties,
    summary="Get internal technical properties for a fabric",
)
async def get_fabric_properties(
    fabric_id: UUID,
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(get_current_role),
) -> FabricProperties:
    """Return the technical properties of a fabric for downstream module consumption.

    Accessible to any authenticated role (client or catalog_manager).

    - Returns HTTP 404 if the fabric does not exist (Req 7 AC2).
    - Returns properties even when ``fabric_status = archived``, because
      historical orders may still reference archived fabrics (Req 7 AC4).
    - The ``reference_rigidity_level`` is sourced from the fabric's parent
      FABRIC_CATEGORY record (P7.2).
    - The ``fabric_elasticity_rate`` is returned exactly as stored (P7.1).

    Implements Req 7 AC1–4.
    """
    fabric = await crud.get_fabric(db, fabric_id)
    if fabric is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fabric not found.",
        )

    return FabricProperties(
        fabric_id=fabric.fabric_id,
        fabric_elasticity_rate=float(fabric.fabric_elasticity_rate),
        category_id=fabric.category_id,
        reference_rigidity_level=fabric.category.reference_rigidity_level,
    )


# ===========================================================================
# Module 4 — Pattern Catalog endpoints  (Task 16)
# ===========================================================================

# ---------------------------------------------------------------------------
# Helper: build ZoneItem/FabricItem lists from an ORM Model instance
# ---------------------------------------------------------------------------


def _zone_items(model) -> list[ZoneItem]:
    """Return ZoneItem list from the model's eagerly-loaded zones."""
    return [ZoneItem(zone_id=z.zone_id, zone_name=z.zone_name) for z in model.zones]


async def _model_detail_out(db: AsyncSession, model) -> ModelDetailOut:
    """Build a ModelDetailOut from an ORM Model instance.

    Resolves fabric names via a JOIN against the fabrics table so that the
    response never contains empty fabric_name strings (fix for issue #4).
    """
    fabrics_raw = await crud.get_fabrics_for_model(db, model.model_id)
    return ModelDetailOut(
        model_id=model.model_id,
        model_name=model.model_name,
        description=model.description,
        garment_type=model.garment_type.value if hasattr(model.garment_type, "value") else model.garment_type,
        cut_type=model.cut_type.value if hasattr(model.cut_type, "value") else model.cut_type,
        status=model.status.value if hasattr(model.status, "value") else model.status,
        version=model.version,
        photo_url=model.photo_url,
        zones=_zone_items(model),
        fabrics=[
            FabricItem(fabric_id=f["fabric_id"], fabric_name=f["fabric_name"])
            for f in fabrics_raw
        ],
    )


# ---------------------------------------------------------------------------
# POST /models/init  — Req 1 AC1–8
# ---------------------------------------------------------------------------


@router.post(
    "/models/init",
    response_model=ModelInitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit inspiration image and generate Draft model profile",
    tags=["models"],
)
async def init_model(
    image: UploadFile = File(..., description="Inspiration garment image (JPEG, PNG, or WebP; max 10 MB)"),
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_client),
    x_user_id: Optional[str] = Header(None, description="Authenticated user UUID (set by Module 1)"),
) -> ModelInitResponse:
    """Upload an inspiration image and create a Draft model profile via AI analysis.

    Validates the image format (JPEG/PNG/WebP) and size (≤ 10 MB), uploads it to
    Supabase Storage, invokes the AI Analyzer synchronously, maps predicted zones,
    computes a sequential model_name, and inserts the MODEL row in one transaction.

    Implements Req 1 AC1–8.

    Error codes:
    - 401: missing / unrecognised role header.
    - 403: caller role is not ``client``.
    - 422: invalid image format/size or AI confidence < 0.70.
    - 500: Supabase Storage upload failure.
    - 503: AI Analyzer unreachable.
    """
    # `creator_id` is taken from the x-user-id header set by Module 1.
    # Fall back to a placeholder UUID if the header is absent (allows local testing).
    creator_id: str = x_user_id or "00000000-0000-0000-0000-000000000000"

    image_bytes: bytes = await image.read()
    filename: str = image.filename or "upload"
    content_type: str = image.content_type or "application/octet-stream"

    return await service.init_model(
        db=db,
        image_bytes=image_bytes,
        filename=filename,
        content_type=content_type,
        creator_id=creator_id,
    )


# ---------------------------------------------------------------------------
# GET /models  — Req 2 AC1–7
# ---------------------------------------------------------------------------


@router.get(
    "/models",
    response_model=ModelListOut,
    summary="List Published garment models",
    tags=["models"],
)
async def list_models(
    garment_type: Optional[GarmentTypeEnum] = Query(
        None,
        description="Filter by garment type (e.g. Dress, Shirt).",
    ),
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_authenticated),
) -> ModelListOut:
    """Return all Published models, ordered by model_name asc / model_id asc.

    Only models with ``status = Published`` are included; Draft and Archived
    models are excluded (Req 2 AC3).  Optionally filter by ``garment_type``.

    Implements Req 2 AC1–7.

    Error codes:
    - 401: unauthenticated request.
    - 422: invalid garment_type enum value.
    """
    garment_type_value: Optional[str] = garment_type.value if garment_type is not None else None

    items, total = await crud.list_models(db, garment_type=garment_type_value)

    list_items = [
        ModelListItem(
            model_id=m.model_id,
            model_name=m.model_name,
            garment_type=m.garment_type.value if hasattr(m.garment_type, "value") else m.garment_type,
            cut_type=m.cut_type.value if hasattr(m.cut_type, "value") else m.cut_type,
            version=m.version,
            photo_url=m.photo_url,
        )
        for m in items
    ]

    return ModelListOut(total=total, items=list_items)


# ---------------------------------------------------------------------------
# GET /models/{model_id}  — Req 3 AC1–6
# ---------------------------------------------------------------------------


@router.get(
    "/models/{model_id}",
    response_model=ModelDetailOut,
    summary="Get Published model detail (client-facing)",
    tags=["models"],
)
async def get_model(
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_authenticated),
) -> ModelDetailOut:
    """Return full profile for a Published model.

    Returns HTTP 404 for Draft, Archived, or non-existent models (Req 3 AC2–4).
    The ``model_id`` path parameter must be a valid UUID (HTTP 422 otherwise).

    Implements Req 3 AC1–6.

    Error codes:
    - 401: unauthenticated request.
    - 404: model not found, or Draft/Archived.
    - 422: model_id is not a valid UUID.
    """
    model = await crud.get_model(db, model_id)

    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found.",
        )

    model_status = model.status.value if hasattr(model.status, "value") else model.status
    if model_status != "Published":
        # Draft and Archived are invisible to client-facing endpoint (Req 3 AC3–4)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found.",
        )

    return await _model_detail_out(db, model)


# ---------------------------------------------------------------------------
# PATCH /models/{model_id}  — Req 4 AC1–8; Req 7 AC1–6
# ---------------------------------------------------------------------------


@router.patch(
    "/models/{model_id}",
    response_model=ModelDetailOut,
    summary="Edit a Draft or Published model (admin)",
    tags=["models"],
)
async def patch_model(
    model_id: UUID,
    data: ModelUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_admin),
) -> ModelDetailOut:
    """Apply a partial update to a model.

    Behaviour is status-aware (delegated to ``service.edit_model``):
    - **Draft** → edit fields in-place, no snapshot.
    - **Published** → write snapshot then apply edits atomically.
    - **Archived** → 409.

    All field validations (enum, length) are enforced before any DB write.

    Implements Req 4 AC1–8; Req 7 AC1–6.

    Error codes:
    - 401: unauthenticated.
    - 403: caller role is not ``administrator``.
    - 404: model not found.
    - 409: model is Archived (or unexpected status).
    - 422: invalid field values.
    - 500: snapshot write failure (Published path only).
    """
    model = await service.edit_model(db=db, model_id=model_id, update_data=data)
    return await _model_detail_out(db, model)


# ---------------------------------------------------------------------------
# PUT /models/{model_id}/zones  — Req 4 AC9–11
# ---------------------------------------------------------------------------


@router.put(
    "/models/{model_id}/zones",
    summary="Assign critical zones to a model (admin)",
    tags=["models"],
)
async def assign_zones(
    model_id: UUID,
    body: ZoneAssignmentRequest,
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_admin),
) -> dict:
    """Atomically replace the critical zone assignments for a model.

    Accepts an empty ``zone_ids`` list to clear all zone assignments (Req 4 AC11).
    Every ``zone_id`` must exist in the ``critical_zone`` reference table (Req 4 AC10).

    Implements Req 4 AC9–11.

    Error codes:
    - 401: unauthenticated.
    - 403: caller role is not ``administrator``.
    - 404: model not found.
    - 422: unknown zone_id.
    """
    zones = await service.assign_zones(db=db, model_id=model_id, zone_ids=body.zone_ids)
    return {
        "zones": [
            ZoneItem(zone_id=z.zone_id, zone_name=z.zone_name).model_dump()
            for z in zones
        ]
    }


# ---------------------------------------------------------------------------
# PUT /models/{model_id}/fabrics  — Req 5 AC1–8
# ---------------------------------------------------------------------------


@router.put(
    "/models/{model_id}/fabrics",
    summary="Assign compatible fabrics to a model (admin)",
    tags=["models"],
)
async def assign_fabrics(
    model_id: UUID,
    body: FabricAssignmentRequest,
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_admin),
) -> dict:
    """Atomically replace the fabric assignments for a model.

    Each ``fabric_id`` is validated against Module 3 (same process, direct CRUD
    call): must exist and have ``fabric_status = available``.  Duplicates are
    deduplicated before validation.  An empty list clears all assignments.

    Implements Req 5 AC1–8.

    Error codes:
    - 401: unauthenticated.
    - 403: caller role is not ``administrator``.
    - 404: model not found.
    - 422: unknown or unavailable fabric_id.
    """
    fabrics = await service.assign_fabrics(
        db=db, model_id=model_id, fabric_ids=body.fabric_ids
    )
    return {
        "fabrics": [
            FabricItem(fabric_id=f["fabric_id"], fabric_name=f["fabric_name"]).model_dump()
            for f in fabrics
        ]
    }


# ---------------------------------------------------------------------------
# POST /models/{model_id}/publish  — Req 6 AC1–8; Req 7 AC3–4
# ---------------------------------------------------------------------------


@router.post(
    "/models/{model_id}/publish",
    response_model=ModelDetailOut,
    summary="Publish or re-publish a model (admin)",
    tags=["models"],
)
async def publish_model(
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_admin),
) -> ModelDetailOut:
    """Publish a Draft model or increment version on a Published model.

    Runs the completeness gate before any state change:
    - ≥ 1 critical zone required.
    - ≥ 1 compatible fabric required.

    Implements Req 6 AC1–8; Req 7 AC3–4.

    Error codes:
    - 401: unauthenticated.
    - 403: caller role is not ``administrator``.
    - 404: model not found.
    - 409: model is Archived.
    - 422: completeness gate failure (missing zones / fabrics).
    """
    try:
        model = await service.publish_model(db=db, model_id=model_id)
    except MissingZonesAndFabricsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except MissingZonesError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except MissingFabricsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return await _model_detail_out(db, model)


# ---------------------------------------------------------------------------
# POST /models/{model_id}/archive  — Req 8 AC1, AC5–8
# ---------------------------------------------------------------------------


@router.post(
    "/models/{model_id}/archive",
    response_model=ArchiveOut,
    summary="Archive a Draft or Published model (admin)",
    tags=["models"],
)
async def archive_model(
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_admin),
) -> ArchiveOut:
    """Transition a Draft or Published model to ``status = Archived``.

    Archived models are excluded from ``GET /models`` and return HTTP 404 on
    ``GET /models/{id}`` (client-facing).  The internal constraints endpoint
    still serves them.

    Implements Req 8 AC1, AC5–8.

    Error codes:
    - 401: unauthenticated.
    - 403: caller role is not ``administrator``.
    - 404: model not found.
    - 409: model already Archived.
    - 500: DB error during status update.
    """
    model = await service.archive_model(db=db, model_id=model_id)

    return ArchiveOut(
        model_id=model.model_id,
        status=model.status.value if hasattr(model.status, "value") else model.status,
    )


# ---------------------------------------------------------------------------
# GET /models/{model_id}/constraints  — Req 9 AC1–7  (internal / downstream)
# ---------------------------------------------------------------------------


@router.get(
    "/models/{model_id}/constraints",
    response_model=ConstraintsOut,
    summary="Get model constraints for downstream modules (internal)",
    tags=["models"],
)
async def get_model_constraints(
    model_id: UUID,
    db: AsyncSession = Depends(get_db),
    _role: str = Depends(require_authenticated),
) -> ConstraintsOut:
    """Return model constraints for downstream modules (Module 6 / 7).

    Serves both **Published** and **Archived** models (Req 9 AC1–2).
    Returns HTTP 404 for Draft models (Req 9 AC3) and non-existent models
    (Req 9 AC4).

    Implements Req 9 AC1–7.

    Error codes:
    - 401: unauthenticated.
    - 404: Draft or non-existent model.
    - 422: model_id is not a valid UUID.
    """
    model = await crud.get_model(db, model_id)

    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found.",
        )

    model_status = model.status.value if hasattr(model.status, "value") else model.status

    # Draft profiles are NOT served to downstream modules (Req 9 AC3)
    if model_status == "Draft":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Model not found.",
        )

    # Build fabric items from the live join — need fabric_name so use get_fabrics_for_model
    fabrics_raw = await crud.get_fabrics_for_model(db, model_id)

    return ConstraintsOut(
        model_id=model.model_id,
        model_name=model.model_name,
        version=model.version,
        garment_type=model.garment_type.value if hasattr(model.garment_type, "value") else model.garment_type,
        cut_type=model.cut_type.value if hasattr(model.cut_type, "value") else model.cut_type,
        zones=_zone_items(model),
        fabrics=[
            FabricItem(fabric_id=f["fabric_id"], fabric_name=f["fabric_name"])
            for f in fabrics_raw
        ],
    )

"""
Top-level APIRouter for the auth_catalogues module.
Mounts the auth, profile, and measurement sub-routers.

Design reference: Internal Package Layout (design.md)
"""
from fastapi import APIRouter

from app.modules.auth_catalogues.auth.router import router as auth_router
from app.modules.auth_catalogues.profile.router import router as profile_router
from app.modules.auth_catalogues.measurement.router import router as measurement_router

router = APIRouter()


@router.get("/", tags=["auth_catalogues"])
def health_check():
    """Health check for the auth_catalogues module."""
    return {"status": "auth_catalogues module OK"}

# ── Auth sub-router: /auth/* ──────────────────────────────────────────────────
router.include_router(auth_router, prefix="/auth", tags=["auth"])

# ── Profile sub-router: /users/* and /admin/* (no prefix — paths are full) ───
router.include_router(profile_router, tags=["profile"])

# ── Measurement sub-router: /users/me/mensurations, /users/{cni}/mensurations ─
router.include_router(measurement_router, tags=["measurement"])
