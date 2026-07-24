"""
CRUD layer for the Fabric Catalog (Module 3) and Pattern Catalog (Module 4).

All functions are pure database queries with no business logic.
Business-logic guards (e.g. 409 on non-empty category delete, 404 guard on
missing category filter, 409 on unavailable fabric) live in service.py.

Module 3 — Category functions:
    get_category              — fetch a single FabricCategory by UUID
    list_categories           — return all FabricCategory rows
    create_category           — insert a new FabricCategory row
    update_category           — partial-update a FabricCategory row
    delete_category           — permanently delete a FabricCategory row
    count_fabrics_in_category — return the number of Fabric rows in a category

Module 3 — Fabric functions:
    get_fabric                — fetch a single Fabric by UUID (with category eager-loaded)
    list_available_fabrics    — return available Fabric rows (optional category filter)
    create_fabric             — insert a new Fabric row (status defaults to 'available')
    update_fabric             — partial-update a Fabric row

Module 4 — Pattern Catalog functions:
    create_model              — insert a new Model row with initial zone associations
    get_model                 — fetch a single Model by UUID
    list_models               — return Published models with optional garment_type filter
    update_model              — partial-update a Model row
    set_zones                 — atomically replace MODEL_CRITICAL_ZONE entries
    get_zones_for_model       — return CriticalZone rows for a model
    set_fabrics               — atomically replace MODEL_FABRIC entries
    get_fabrics_for_model     — return [{fabric_id, fabric_name}] dicts for a model
    create_snapshot           — read live state and write a MODEL_SNAPSHOT row
    count_zones               — count MODEL_CRITICAL_ZONE entries for a model
    count_fabrics             — count MODEL_FABRIC entries for a model
"""

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.auth_catalogues.models import (
    CriticalZone,
    Fabric,
    FabricCategory,
    Model,
    ModelFabric,
    ModelSnapshot,
    model_critical_zone_table,
)
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


# ===========================================================================
# Module 4 — Pattern Catalog CRUD functions
# ===========================================================================
# Pure database queries with no business logic.
# Business-logic guards (completeness gate, status-machine transitions,
# snapshot atomicity) live in service.py.
# ===========================================================================


async def create_model(
    db: AsyncSession,
    model_data: dict,
) -> Model:
    """Insert a new Model row and return the ORM instance.

    *model_data* is a plain dict whose keys match Model column names.
    The caller is responsible for populating all required fields
    (model_name, garment_type, cut_type, photo_url, creator_id) as well as
    the optional ``zone_ids`` list used to seed MODEL_CRITICAL_ZONE entries.

    Zone associations (if any) are inserted in the same transaction so the
    returned model already has ``model.zones`` populated.

    Implements: design §9 (crud.py) — create_model.
    """
    zone_ids: list[UUID] = model_data.pop("zone_ids", [])

    new_model = Model(**model_data)
    db.add(new_model)
    # Flush so that model_id is assigned before inserting zone rows.
    await db.flush()

    if zone_ids:
        await db.execute(
            model_critical_zone_table.insert(),
            [{"model_id": new_model.model_id, "zone_id": zid} for zid in zone_ids],
        )

    await db.commit()
    # Re-fetch with all relationships eager-loaded.
    return await get_model(db, new_model.model_id)


async def get_model(db: AsyncSession, model_id: UUID) -> Model | None:
    """Return the Model with the given *model_id*, or ``None`` if not found.

    ``zones`` and ``fabric_associations`` are eager-loaded via ``selectinload``
    so callers can access them without triggering additional lazy queries.

    Implements: design §9 (crud.py) — get_model.
    """
    result = await db.execute(
        select(Model)
        .options(
            selectinload(Model.zones),
            selectinload(Model.fabric_associations),
        )
        .where(Model.model_id == model_id)
    )
    return result.scalar_one_or_none()


async def list_models(
    db: AsyncSession,
    garment_type: str | None = None,
) -> tuple[list[Model], int]:
    """Return Published Model rows ordered by model_name / model_id, plus total count.

    Only rows with ``status = 'Published'`` are returned (Req 2 AC1).
    An optional *garment_type* string value narrows the results (Req 2 AC5).
    The ``total`` reflects the count *after* the garment_type filter.

    Returns a ``(items, total)`` tuple.  Items are capped at 100 (Req 2 AC1).

    Implements: design §9 (crud.py) — list_models; Req 2 AC1.
    """
    base_stmt = (
        select(Model)
        .options(
            selectinload(Model.zones),
            selectinload(Model.fabric_associations),
        )
        .where(Model.status == "Published")
    )

    if garment_type is not None:
        base_stmt = base_stmt.where(Model.garment_type == garment_type)

    # Count query — re-use the same filter conditions.
    count_stmt = select(func.count()).select_from(
        base_stmt.with_only_columns(Model.model_id).subquery()
    )
    total_result = await db.execute(count_stmt)
    total: int = total_result.scalar_one()

    # Data query with ordering + limit.
    data_stmt = (
        base_stmt
        .order_by(Model.model_name.asc(), Model.model_id.asc())
        .limit(100)
    )
    data_result = await db.execute(data_stmt)
    items = list(data_result.scalars().all())

    return items, total


async def update_model(
    db: AsyncSession,
    model_id: UUID,
    fields: dict,
) -> Model | None:
    """Apply only the provided *fields* to an existing Model row.

    Returns the updated ORM instance (with relationships eager-loaded),
    or ``None`` if the model does not exist.

    Enum values may be passed as Python enum instances or plain strings —
    both are handled gracefully.

    Implements: design §9 (crud.py) — update_model.
    """
    model = await get_model(db, model_id)
    if model is None:
        return None

    for field, value in fields.items():
        # Convert enum instances to their string value for SA storage.
        if hasattr(value, "value"):
            value = value.value
        setattr(model, field, value)

    await db.commit()
    return await get_model(db, model_id)


async def set_zones(
    db: AsyncSession,
    model_id: UUID,
    zone_ids: list[UUID],
) -> None:
    """Atomically replace all MODEL_CRITICAL_ZONE entries for *model_id*.

    Deletes every existing row for the model then inserts the provided
    *zone_ids* in a single round-trip.  An empty *zone_ids* list clears
    all zone assignments (Req 4 AC11).

    The caller is responsible for verifying that each zone_id exists in the
    CRITICAL_ZONE table before calling this function (Req 4 AC10).

    Implements: design §9 (crud.py) — set_zones; Req 4 AC9–11.
    """
    # Delete all current associations for this model.
    await db.execute(
        delete(model_critical_zone_table).where(
            model_critical_zone_table.c.model_id == model_id
        )
    )

    # Insert the new set (no-op if zone_ids is empty).
    if zone_ids:
        await db.execute(
            model_critical_zone_table.insert(),
            [{"model_id": model_id, "zone_id": zid} for zid in zone_ids],
        )

    await db.commit()


async def get_zones_for_model(
    db: AsyncSession,
    model_id: UUID,
) -> list[CriticalZone]:
    """Return the CriticalZone rows currently assigned to *model_id*.

    Results are ordered by zone_name ascending for consistent responses.

    Implements: design §9 (crud.py) — get_zones_for_model.
    """
    result = await db.execute(
        select(CriticalZone)
        .join(
            model_critical_zone_table,
            model_critical_zone_table.c.zone_id == CriticalZone.zone_id,
        )
        .where(model_critical_zone_table.c.model_id == model_id)
        .order_by(CriticalZone.zone_name.asc())
    )
    return list(result.scalars().all())


async def set_fabrics(
    db: AsyncSession,
    model_id: UUID,
    fabric_ids: list[UUID],
) -> None:
    """Atomically replace all MODEL_FABRIC entries for *model_id*.

    Deletes every existing ModelFabric row for the model then inserts the
    provided *fabric_ids* in a single round-trip.  An empty *fabric_ids*
    list clears all fabric assignments (Req 5 AC4).

    The caller is responsible for deduplicating *fabric_ids* and validating
    each against Module 3 before calling this function (Req 5 AC1–3, AC8).

    Implements: design §9 (crud.py) — set_fabrics; Req 5 AC1.
    """
    await db.execute(
        delete(ModelFabric).where(ModelFabric.model_id == model_id)
    )

    if fabric_ids:
        db.add_all(
            [ModelFabric(model_id=model_id, fabric_id=fid) for fid in fabric_ids]
        )

    await db.commit()


async def get_fabrics_for_model(
    db: AsyncSession,
    model_id: UUID,
) -> list[dict]:
    """Return a list of ``{fabric_id, fabric_name}`` dicts for *model_id*.

    The ``fabric_name`` is resolved by joining against the ``fabrics`` table
    (Module 3).  If a fabric_id stored in MODEL_FABRIC no longer exists in
    the ``fabrics`` table (e.g. hard-deleted), it is silently omitted —
    this preserves Module 3 loose-coupling (design §2.4).

    Results are ordered by fabric_name ascending.

    Implements: design §9 (crud.py) — get_fabrics_for_model.
    """
    result = await db.execute(
        select(ModelFabric.fabric_id, Fabric.fabric_name)
        .join(Fabric, Fabric.fabric_id == ModelFabric.fabric_id, isouter=True)
        .where(ModelFabric.model_id == model_id)
        .order_by(Fabric.fabric_name.asc())
    )
    rows = result.all()
    return [
        {"fabric_id": row.fabric_id, "fabric_name": row.fabric_name}
        for row in rows
        if row.fabric_name is not None  # drop orphaned references
    ]


async def create_snapshot(
    db: AsyncSession,
    model: Model,
) -> ModelSnapshot:
    """Read the live zones + fabrics for *model* and write a MODEL_SNAPSHOT row.

    This function is called **inside a caller-managed transaction** (service
    layer opens the transaction via ``async with db.begin()``).  It does NOT
    call ``db.commit()`` itself so the snapshot and the subsequent MODEL UPDATE
    are committed atomically by the caller.

    The snapshot captures (Req 7 AC8):
      - All scalar fields from the live MODEL row.
      - A JSONB array of ``{zone_id, zone_name}`` from MODEL_CRITICAL_ZONE.
      - A JSONB array of ``{fabric_id, fabric_name}`` from MODEL_FABRIC / fabrics.

    Raises any SQLAlchemy exception on DB failure — the caller must catch and
    rollback (Req 7 AC2; P7.4).

    Implements: design §9 (crud.py) — create_snapshot; Req 7 AC1, AC8.
    """
    # Resolve zones — fetch fresh from DB to guarantee accuracy inside the TX.
    zones_result = await db.execute(
        select(CriticalZone.zone_id, CriticalZone.zone_name)
        .join(
            model_critical_zone_table,
            model_critical_zone_table.c.zone_id == CriticalZone.zone_id,
        )
        .where(model_critical_zone_table.c.model_id == model.model_id)
        .order_by(CriticalZone.zone_name.asc())
    )
    zones_payload = [
        {"zone_id": str(row.zone_id), "zone_name": row.zone_name}
        for row in zones_result.all()
    ]

    # Resolve fabrics — join against the Module 3 fabrics table.
    fabrics_result = await db.execute(
        select(ModelFabric.fabric_id, Fabric.fabric_name)
        .join(Fabric, Fabric.fabric_id == ModelFabric.fabric_id, isouter=True)
        .where(ModelFabric.model_id == model.model_id)
        .order_by(Fabric.fabric_name.asc())
    )
    fabrics_payload = [
        {"fabric_id": str(row.fabric_id), "fabric_name": row.fabric_name}
        for row in fabrics_result.all()
        if row.fabric_name is not None
    ]

    # Determine the garment/cut type string values (may be enum instances or strings).
    garment_type_val = (
        model.garment_type.value
        if hasattr(model.garment_type, "value")
        else model.garment_type
    )
    cut_type_val = (
        model.cut_type.value
        if hasattr(model.cut_type, "value")
        else model.cut_type
    )
    status_val = (
        model.status.value
        if hasattr(model.status, "value")
        else model.status
    )

    snapshot = ModelSnapshot(
        model_id=model.model_id,
        snapshot_version=model.version,
        model_name=model.model_name,
        description=model.description,
        garment_type=garment_type_val,
        cut_type=cut_type_val,
        photo_url=model.photo_url,
        status=status_val,
        creator_id=model.creator_id,
        zones=zones_payload,
        fabrics=fabrics_payload,
    )

    db.add(snapshot)
    # Flush to assign snapshot_id and surface DB constraint errors early,
    # while still inside the caller's transaction.
    await db.flush()
    return snapshot


async def count_zones(db: AsyncSession, model_id: UUID) -> int:
    """Return the number of MODEL_CRITICAL_ZONE entries for *model_id*.

    Used by the completeness gate (service layer) before publishing.

    Implements: design §9 (crud.py) — count_zones; Req 6 AC2, AC4.
    """
    result = await db.execute(
        select(func.count()).where(
            model_critical_zone_table.c.model_id == model_id
        )
    )
    return result.scalar_one()


async def count_fabrics(db: AsyncSession, model_id: UUID) -> int:
    """Return the number of MODEL_FABRIC entries for *model_id*.

    Used by the completeness gate (service layer) before publishing.

    Implements: design §9 (crud.py) — count_fabrics; Req 6 AC3, AC4.
    """
    result = await db.execute(
        select(func.count()).where(ModelFabric.model_id == model_id)
    )
    return result.scalar_one()
