"""
SQLAlchemy ORM models for the Fabric Catalog module.

Tables:
    fabric_categories — reference catalog of fabric categories
    fabrics           — individual fabric references

Both models inherit from the shared `Base` declared in `app.database`.
"""

import uuid
from sqlalchemy import Column, String, Numeric, Text, ForeignKey, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


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
