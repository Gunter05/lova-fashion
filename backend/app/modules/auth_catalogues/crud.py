"""
CRUD layer for the Fabric Catalog module.

All functions are pure database queries with no business logic.
Business-logic guards (e.g. 409 on non-empty category delete, 404 guard on
missing category filter, 409 on unavailable fabric) live in service.py.

Category functions:
    get_category              — fetch a single FabricCategory by UUID
    list_categories           — return all FabricCategory rows
    create_category           — insert a new FabricCategory row
    update_category           — partial-update a FabricCategory row
    delete_category           — permanently delete a FabricCategory row
    count_fabrics_in_category — return the number of Fabric rows in a category

Fabric functions:
    get_fabric                — fetch a single Fabric by UUID (with category eager-loaded)
    list_available_fabrics    — return available Fabric rows (optional category filter)
    create_fabric             — insert a new Fabric row (status defaults to 'available')
    update_fabric             — partial-update a Fabric row
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.auth_catalogues.models import Fabric, FabricCategory
from app.modules.auth_catalogues.schemas import (
    CategoryCreate,
    CategoryUpdate,
    FabricCreate,
    FabricUpdate,
)


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


async def get_category(db: AsyncSession, category_id: UUID) -> FabricCategory | None:
    """Return the FabricCategory with the given *category_id*, or ``None`` if not found."""
    result = await db.execute(
        select(FabricCategory).where(FabricCategory.category_id == category_id)
    )
    return result.scalar_one_or_none()


async def list_categories(db: AsyncSession) -> list[FabricCategory]:
    """Return all FabricCategory rows, ordered by *category_name* ascending."""
    result = await db.execute(
        select(FabricCategory).order_by(FabricCategory.category_name)
    )
    return list(result.scalars().all())


async def count_fabrics_in_category(db: AsyncSession, category_id: UUID) -> int:
    """Return the number of Fabric rows whose *category_id* matches the given UUID.

    Used by the service layer before allowing a category deletion (Req 4 AC6–7).
    """
    result = await db.execute(
        select(func.count()).where(Fabric.category_id == category_id)
    )
    return result.scalar_one()


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------


async def create_category(
    db: AsyncSession, data: CategoryCreate
) -> FabricCategory:
    """Insert a new FabricCategory row, commit, refresh and return the ORM instance.

    Implements Req 4 AC1.
    """
    category = FabricCategory(
        category_name=data.category_name,
        category_description=data.category_description,
        # Store the enum value string (e.g. "rigid", "semi-stretch", "stretch")
        reference_rigidity_level=data.reference_rigidity_level.value,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


async def update_category(
    db: AsyncSession, category_id: UUID, data: CategoryUpdate
) -> FabricCategory | None:
    """Apply only the provided (non-None) fields to an existing FabricCategory row.

    Returns the updated ORM instance, or ``None`` if the category does not exist.
    Implements Req 4 AC4.
    """
    category = await get_category(db, category_id)
    if category is None:
        return None

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        # Enum fields must be stored as their string value
        if hasattr(value, "value"):
            value = value.value
        setattr(category, field, value)

    await db.commit()
    await db.refresh(category)
    return category


async def delete_category(db: AsyncSession, category_id: UUID) -> bool:
    """Permanently delete the FabricCategory row with the given *category_id*.

    Returns ``True`` on success, ``False`` if the category was not found.

    The caller (service layer) is responsible for checking that no fabrics
    reference this category before invoking this function (Req 4 AC6–7).
    """
    category = await get_category(db, category_id)
    if category is None:
        return False

    await db.delete(category)
    await db.commit()
    return True


# ===========================================================================
# Fabric CRUD functions
# ===========================================================================
# Pure database queries with no business logic.
# Business-logic guards (status rules, 409 on unavailable, 404 guard on
# missing category filter) live in service.py.
#
# Functions:
#     get_fabric         — fetch a single Fabric by UUID, with category joined
#     create_fabric      — insert a new Fabric row (status defaults to 'available')
#     update_fabric      — partial-update a Fabric row
# ===========================================================================

async def get_fabric(db: AsyncSession, fabric_id: UUID) -> Fabric | None:
    """Return the Fabric with the given *fabric_id*, eagerly loading its category.

    Returns ``None`` if the fabric does not exist.
    The category relationship is loaded via ``selectinload`` so callers can
    access ``fabric.category.category_name`` and
    ``fabric.category.reference_rigidity_level`` without issuing additional
    lazy-load queries.
    """
    result = await db.execute(
        select(Fabric)
        .options(selectinload(Fabric.category))
        .where(Fabric.fabric_id == fabric_id)
    )
    return result.scalar_one_or_none()


async def list_available_fabrics(
    db: AsyncSession, category_id: UUID | None = None
) -> list[Fabric]:
    """Return all fabrics whose ``fabric_status`` is ``'available'``.

    Each returned ``Fabric`` instance has its ``category`` relationship
    eagerly loaded (``selectinload``) so callers can access
    ``fabric.category.category_name``.

    If *category_id* is provided, only fabrics belonging to that category
    are returned.  **No 404 guard is performed here** — callers that need the
    guard (i.e. client-facing endpoints) must call
    ``service.list_available_fabrics`` instead, which validates the category
    first.

    Implements Req 1 AC1–2 (pure query layer).
    """
    stmt = (
        select(Fabric)
        .options(selectinload(Fabric.category))
        .where(Fabric.fabric_status == "available")
    )
    if category_id is not None:
        stmt = stmt.where(Fabric.category_id == category_id)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_fabric(db: AsyncSession, data: FabricCreate) -> Fabric:
    """Insert a new Fabric row and return the ORM instance with its category loaded.

    The new fabric always starts with ``fabric_status = 'available'`` (Req 5 AC1).
    After commit the category relationship is eagerly re-loaded so the caller
    can access ``fabric.category`` immediately.
    """
    fabric = Fabric(
        fabric_name=data.fabric_name,
        fabric_elasticity_rate=data.fabric_elasticity_rate,
        fabric_weight=data.fabric_weight,
        fabric_composition=data.fabric_composition,
        fabric_unit_price=data.fabric_unit_price,
        category_id=data.category_id,
        fabric_status="available",  # Req 5 AC1 — default status
    )
    db.add(fabric)
    await db.commit()
    # Re-fetch with the category eagerly loaded so the caller has a complete object.
    return await get_fabric(db, fabric.fabric_id)


async def update_fabric(
    db: AsyncSession, fabric_id: UUID, data: FabricUpdate
) -> Fabric | None:
    """Apply only the provided (non-None) fields to an existing Fabric row.

    Returns the updated ORM instance with category eagerly loaded, or
    ``None`` if the fabric does not exist.
    Implements Req 5 AC7–8.
    """
    fabric = await get_fabric(db, fabric_id)
    if fabric is None:
        return None

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        # Enum fields must be stored as their string value
        if hasattr(value, "value"):
            value = value.value
        setattr(fabric, field, value)

    await db.commit()
    # Re-fetch to get a fresh instance with the updated category relationship.
    return await get_fabric(db, fabric_id)
