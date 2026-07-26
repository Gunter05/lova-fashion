"""
SQLAlchemy ORM models for Module 5 — Ease Allowance Calculation Engine.
Tasks T-02.1, T-02.2 — Design §3.1, §3.2
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
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


# ---------------------------------------------------------------------------
# Module 6 — Fabric / Model / Silhouette Compatibility Engine
# Tasks T-02.1, T-02.2 — Design §Data Models
# ---------------------------------------------------------------------------

class CompatibilityRule(Base):
    """
    Admin-configurable rule that encodes a cut/fabric condition, a mathematical
    threshold expression, a severity level, and an explanation message.

    Task T-02.1 — Requirements 2.1, 2.2, 9.1–9.3, 13.3
    """

    __tablename__ = "compatibility_rules"

    __table_args__ = (
        UniqueConstraint(
            "cut_type",
            "fabric_property",
            "zone_id",
            "is_active",
            name="uq_rule_cut_fabric_zone_active",
        ),
        CheckConstraint(
            "severity_level IN ('Incompatible', 'Reserve')",
            name="ck_rule_severity",
        ),
        CheckConstraint(
            "char_length(mathematical_condition) <= 200",
            name="ck_rule_condition_length",
        ),
        CheckConstraint(
            "char_length(explanation_message) <= 500",
            name="ck_rule_explanation_length",
        ),
    )

    rule_id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cut_type: str = Column(String(30), nullable=False)
    # "Fitted" | "Semi-fitted" | "Loose"
    fabric_property: str = Column(String(30), nullable=False)
    # "rigid" | "semi-stretch" | "stretch"
    zone_id: uuid.UUID | None = Column(
        UUID(as_uuid=True),
        ForeignKey("critical_zone.zone_id"),
        nullable=True,
    )
    mathematical_condition: str = Column(String(200), nullable=False)
    severity_level: str = Column(String(20), nullable=False)
    explanation_message: str | None = Column(Text, nullable=True)
    is_active: bool = Column(Boolean, nullable=False, default=True)
    version: int = Column(Integer, nullable=False, default=1)
    admin_id: uuid.UUID = Column(
        UUID(as_uuid=True), nullable=False
    )  # logical FK → auth.users
    created_at: datetime = Column(
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
            f"<CompatibilityRule {self.rule_id!r} "
            f"cut={self.cut_type!r} fabric={self.fabric_property!r} "
            f"severity={self.severity_level!r} active={self.is_active}>"
        )


class ModelMorphology(Base):
    """
    Association table — links a garment Model to a body Morphology with a
    suitability score (MODEL_MORPHOLOGY_LINK).

    Task T-02.2 — Requirements 4.1–4.5, 13.3
    """

    __tablename__ = "model_morphology"

    __table_args__ = (
        CheckConstraint(
            "suitability_score IN ('Ideal', 'Flattering', 'Avoid')",
            name="ck_morphology_score",
        ),
    )

    model_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("model.model_id", ondelete="CASCADE"),
        primary_key=True,
    )
    morphology_id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True
    )  # logical FK → body_shapes
    suitability_score: str = Column(String(15), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ModelMorphology model={self.model_id!r} "
            f"morphology={self.morphology_id!r} score={self.suitability_score!r}>"
        )


class VerdictEvaluation(Base):
    """
    Persisted record of one compatibility evaluation, keyed by evaluation_id.
    Immutable after creation — rule updates do not alter past evaluations.

    Task T-02.2 — Requirements 5.1–5.6, 7.1–7.7, 12.1–12.4, 13.3
    """

    __tablename__ = "verdict_evaluations"

    __table_args__ = (
        CheckConstraint(
            "global_status IN ('Compatible','Compatible_with_Reservations',"
            "'Incompatible','Indeterminate','Failed')",
            name="ck_evaluation_global_status",
        ),
    )

    evaluation_id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    global_status: str = Column(String(40), nullable=False)
    missing_data_log: str | None = Column(Text, nullable=True)
    fabric_recommendation: str | None = Column(String(50), nullable=True)

    # Non-nullable upstream references (Requirement 7.3)
    client_id: uuid.UUID = Column(UUID(as_uuid=True), nullable=False)
    model_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("model.model_id"),
        nullable=False,
    )
    fabric_id: uuid.UUID = Column(
        UUID(as_uuid=True), nullable=False
    )  # logical FK → fabrics
    measurements_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("measurement_adjustments.id"),
        nullable=False,
    )
    morphology_id: uuid.UUID = Column(
        UUID(as_uuid=True), nullable=False
    )  # logical FK → body_shapes

    # Cascade-loaded child rows (Requirement 6.4)
    risk_zones: list["RiskZone"] = relationship(
        "RiskZone",
        back_populates="evaluation",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<VerdictEvaluation {self.evaluation_id!r} "
            f"status={self.global_status!r}>"
        )


class RiskZone(Base):
    """
    Per-zone violation record within a VerdictEvaluation.
    Stores the applied rule, computed variance, localized verdict, and explanation.

    Task T-02.2 — Requirements 3.4, 3.5, 7.2, 13.3
    """

    __tablename__ = "risk_zones"

    __table_args__ = (
        CheckConstraint(
            "localized_verdict IN ('Incompatible', 'Reserve')",
            name="ck_risk_zone_verdict",
        ),
    )

    risk_id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    evaluation_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("verdict_evaluations.evaluation_id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_id: uuid.UUID | None = Column(
        UUID(as_uuid=True),
        ForeignKey("compatibility_rules.rule_id"),
        nullable=True,
    )
    zone_id: uuid.UUID | None = Column(
        UUID(as_uuid=True),
        ForeignKey("critical_zone.zone_id", use_alter=True, name="fk_risk_zone_zone"),
        nullable=True,
    )
    calculated_variance: Decimal = Column(Numeric(8, 4), nullable=False)
    localized_verdict: str = Column(String(20), nullable=False)
    explanation: str = Column(Text, nullable=False)
    rule_version: int = Column(Integer, nullable=False)

    # Back-reference to parent evaluation
    evaluation: "VerdictEvaluation" = relationship(
        "VerdictEvaluation",
        back_populates="risk_zones",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<RiskZone {self.risk_id!r} "
            f"verdict={self.localized_verdict!r} "
            f"evaluation={self.evaluation_id!r}>"
        )
