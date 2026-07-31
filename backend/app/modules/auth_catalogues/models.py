"""
SQLAlchemy ORM models for the Fabric Catalog (Module 3) and Pattern Catalog (Module 4).

Tables (Module 3):
    fabric_categories — reference catalog of fabric categories
    fabrics           — individual fabric references

Tables (Module 4):
    model             — garment pattern / model
    critical_zone     — reference catalog of measurement zones
    model_critical_zone — join table: model ↔ critical_zone
    model_fabric        — join table: model ↔ fabric (Module 3 reference)
    model_snapshot      — immutable audit snapshot of a published model

All models inherit from the shared `Base` declared in `app.database`.
"""

import enum
import uuid
from sqlalchemy import Column, String, Numeric, Text, ForeignKey, TIMESTAMP, func, Integer, Table, UUID
from sqlalchemy import Enum as SAEnum
from sqlalchemy.types import JSON
from sqlalchemy.orm import relationship
from sqlalchemy.ext.compiler import compiles

from app.db.session import Base

@compiles(UUID, "sqlite")
def compile_uuid_sqlite(element, compiler, **kw):
    return "VARCHAR(36)"


class FabricCategory(Base):
    __tablename__ = "fabric_categories"

    category_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_name = Column(String(50), nullable=False)
    category_description = Column(Text, nullable=True)
    # Allowed values: 'rigid' | 'semi-stretch' | 'stretch'  (enforced at schema layer)
    reference_rigidity_level = Column(String(12), nullable=False)
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # One category → many fabrics
    fabrics = relationship("Fabric", back_populates="category")


class Fabric(Base):
    __tablename__ = "fabrics"

    fabric_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fabric_name = Column(String(100), nullable=False)
    # 0.00 – 100.00  (enforced at schema layer)
    fabric_elasticity_rate = Column(Numeric(5, 2), nullable=False)
    # Must be > 0  (enforced at schema layer)
    fabric_weight = Column(Numeric(8, 2), nullable=False)
    fabric_composition = Column(Text, nullable=True)
    # Must be > 0  (enforced at schema layer)
    fabric_unit_price = Column(Numeric(10, 2), nullable=False)
    fabric_photo = Column(Text, nullable=True)
    # Allowed values: 'available' | 'unavailable' | 'archived'
    fabric_status = Column(String(11), nullable=False, default="available")
    category_id = Column(
        UUID(as_uuid=True),
        ForeignKey("fabric_categories.category_id"),
        nullable=False,
    )
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Many fabrics → one category
    category = relationship("FabricCategory", back_populates="fabrics")


# ---------------------------------------------------------------------------
# Module 4 — Pattern Catalog
# ---------------------------------------------------------------------------

# -- Python Enum types -------------------------------------------------------

class GarmentTypeEnum(str, enum.Enum):
    Dress = "Dress"
    Shirt = "Shirt"
    Blouse = "Blouse"
    Trousers = "Trousers"
    Skirt = "Skirt"
    Jacket = "Jacket"
    Coat = "Coat"
    Shorts = "Shorts"
    Suit = "Suit"
    Traditional = "Traditional"


class CutTypeEnum(str, enum.Enum):
    Fitted = "Fitted"
    Semi_fitted = "Semi-fitted"
    Loose = "Loose"


class ModelStatusEnum(str, enum.Enum):
    Draft = "Draft"
    Published = "Published"
    Archived = "Archived"


# -- Association tables (Table objects with composite PKs) -------------------

# model_critical_zone: model ↔ critical_zone
model_critical_zone_table = Table(
    "model_critical_zone",
    Base.metadata,
    Column(
        "model_id",
        UUID(as_uuid=True),
        ForeignKey("model.model_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    ),
    Column(
        "zone_id",
        UUID(as_uuid=True),
        ForeignKey("critical_zone.zone_id"),
        primary_key=True,
        nullable=False,
    ),
)

# -- ORM mapped classes -------------------------------------------------------

class Model(Base):
    """Garment pattern / model."""

    __tablename__ = "model"

    model_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    photo_url = Column(String(255), nullable=False)
    garment_type = Column(
        String(50),
        nullable=False,
    )
    cut_type = Column(
        String(20),
        nullable=False,
    )
    status = Column(
        String(20),
        nullable=False,
        default="Draft",
        server_default="Draft",
    )
    version = Column(Integer, nullable=False, default=1, server_default="1")
    # No ORM-level FK to auth.users (cross-schema — enforced at DB schema level)
    creator_id = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Many-to-many: model ↔ critical_zone
    zones = relationship(
        "CriticalZone",
        secondary=model_critical_zone_table,
        back_populates="models",
        lazy="selectin",
    )

    # Many-to-many: model ↔ fabric (association table only, no ORM class for fabrics side)
    fabric_associations = relationship(
        "ModelFabric",
        back_populates="model",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # One model → many snapshots
    snapshots = relationship(
        "ModelSnapshot",
        back_populates="model_ref",
        cascade="all, delete-orphan",
        lazy="selectin",
        primaryjoin="Model.model_id == ModelSnapshot.model_id",
        foreign_keys="ModelSnapshot.model_id",
    )


class CriticalZone(Base):
    """Reference catalog of measurement critical zones (seed data)."""

    __tablename__ = "critical_zone"

    zone_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zone_name = Column(String(50), nullable=False, unique=True)
    description = Column(Text, nullable=True)

    # Many-to-many back-reference
    models = relationship(
        "Model",
        secondary=model_critical_zone_table,
        back_populates="zones",
    )


class ModelFabric(Base):
    """Association between a Model and a Fabric (Module 3 reference, no DB-level FK)."""

    __tablename__ = "model_fabric"

    model_id = Column(
        UUID(as_uuid=True),
        ForeignKey("model.model_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    fabric_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        nullable=False,
    )

    model = relationship("Model", back_populates="fabric_associations")


class ModelSnapshot(Base):
    """
    Immutable audit snapshot of a Model at the time of a PATCH on a Published model.

    `zones` and `fabrics` are stored as JSONB arrays so the snapshot is
    self-contained even if live rows are later deleted.
    """

    __tablename__ = "model_snapshot"

    snapshot_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Logical reference — no DB FK so snapshots survive if the model row is dropped
    model_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    snapshot_version = Column(Integer, nullable=False)
    model_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    garment_type = Column(String(50), nullable=False)
    cut_type = Column(String(20), nullable=False)
    photo_url = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False)
    creator_id = Column(UUID(as_uuid=True), nullable=False)
    # JSONB columns: [{zone_id, zone_name}, ...]  /  [{fabric_id, fabric_name}, ...]
    zones = Column(JSON, nullable=False)
    fabrics = Column(JSON, nullable=False)
    snapshotted_at = Column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    # Back-reference to the live Model row (may not exist if model was deleted)
    model_ref = relationship(
        "Model",
        back_populates="snapshots",
        primaryjoin="ModelSnapshot.model_id == Model.model_id",
        foreign_keys=[model_id],
    )
