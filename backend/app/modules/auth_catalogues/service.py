"""
Service layer for the Fabric Catalog module.

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

All functions that detect a business-rule violation raise ``HTTPException``
directly; route handlers need no additional error-handling logic.
"""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth_catalogues import crud
from app.modules.auth_catalogues.models import Fabric
from app.modules.auth_catalogues.schemas import SelectionResponse


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
