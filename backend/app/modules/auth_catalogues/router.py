"""
API router for the Fabric Catalog module.

All routes are mounted here and registered in ``backend/main.py`` with the
``/api/v1`` prefix.

Current coverage:
    T6  — Category endpoints  (GET/POST/PATCH/DELETE /categories)
    T7  — Client fabric endpoints  (GET /fabrics, GET /fabrics/{id}, POST /fabrics/{id}/select)
    T8  — Manager fabric endpoints (POST/PATCH/DELETE /fabrics)
    T9  — Photo upload             (POST /fabrics/{id}/photo)

Planned (added in later tasks):
    T10 — Internal properties      (GET /fabrics/{id}/properties)
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.auth_catalogues import crud, service
from app.modules.auth_catalogues.dependencies import get_current_role, require_role
from app.modules.auth_catalogues.schemas import (
    CategoryCreate,
    CategoryResponse,
    CategoryUpdate,
    FabricCreate,
    FabricDetail,
    FabricProperties,
    FabricStatus,
    FabricSummary,
    FabricUpdate,
    SelectionResponse,
)
from app.modules.auth_catalogues import storage
from app.modules.auth_catalogues.storage import StorageUploadError

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
