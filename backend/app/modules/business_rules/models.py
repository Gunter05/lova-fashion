"""
SQLAlchemy ORM models for Module 5 — Ease Allowance Calculation Engine.
Tasks T-02.1, T-02.2 — Design §3.1, §3.2
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    __allow_unmapped__ = True


class EaseRule(Base):
    """
    Reference table — maps elasticity categories to ease delta values.
    Seeded by migration 005. Never modified at runtime (NFR-06).
    Task T-02.1 — Design §3.1
    """

    __tablename__ = "ease_rules"

    elasticity_category: str = Column(String(30), primary_key=True)
    ease_delta_cm: Decimal = Column(Numeric(4, 1), nullable=False)
    description: str | None = Column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EaseRule {self.elasticity_category!r} delta={self.ease_delta_cm} cm>"


class MeasurementAdjustment(Base):
    """
    Ease-adjusted garment cutting measurements for a (session, fabric) pair.
    Stores raw inputs, per-zone ease deltas, and adjusted outputs.
    Task T-02.2 — AC-01.6, AC-03.1, AC-03.2 · Design §3.2
    """

    __tablename__ = "measurement_adjustments"

    __table_args__ = (
        UniqueConstraint("session_id", "fabric_id", name="uq_adjustment_session_fabric"),
        CheckConstraint(
            "ease_source IN ('rule', 'default_fallback')",
            name="ck_measurement_adjustments_ease_source",
        ),
    )

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Upstream references
    session_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("capture_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    fabric_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        nullable=False,   # Logical FK to fabrics table (Module 3)
    )

    # Raw input snapshot (AC-03.2)
    raw_bust_cm: Decimal = Column(Numeric(5, 1), nullable=False)
    raw_waist_cm: Decimal = Column(Numeric(5, 1), nullable=False)
    raw_hips_cm: Decimal = Column(Numeric(5, 1), nullable=False)

    # Per-zone ease applied (AC-03.1)
    bust_ease_cm: Decimal = Column(Numeric(4, 1), nullable=False)
    waist_ease_cm: Decimal = Column(Numeric(4, 1), nullable=False)
    hips_ease_cm: Decimal = Column(Numeric(4, 1), nullable=False)

    # Adjusted output values (NFR-04)
    adjusted_bust_cm: Decimal = Column(Numeric(5, 1), nullable=False)
    adjusted_waist_cm: Decimal = Column(Numeric(5, 1), nullable=False)
    adjusted_hips_cm: Decimal = Column(Numeric(5, 1), nullable=False)

    # Metadata
    ease_source: str = Column(String(30), nullable=False, default="rule")
    calculated_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<MeasurementAdjustment id={self.id!r} "
            f"session={self.session_id!r} fabric={self.fabric_id!r}>"
        )
