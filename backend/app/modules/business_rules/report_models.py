"""
SQLAlchemy ORM model for Module 7 — Final Result & Report (Synthesis).

Defines the `RapportMesure` class mapped to the `rapport_mesure` table.
This module is the sole writer of this table; all other modules are read-only consumers.

Design reference: Data Models §rapport_mesure
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.modules.business_rules.models import Base


class RapportMesure(Base):
    """
    Immutable synthesis record linking one Measurement, one Fabric, and one Garment Model.

    Created exclusively via the `compatibility.evaluated` EventBus event.
    No UPDATE or DELETE operations are permitted on this table.

    Req 1 AC1, AC3, AC5 · Req 8 AC1 · Design §Data Models
    """

    __tablename__ = "rapport_mesure"

    __table_args__ = (
        CheckConstraint(
            "verdict IN ('compatible', 'incompatible', 'minor_adjustments')",
            name="ck_rapport_mesure_verdict",
        ),
        Index("idx_rapport_mesure_user_id_generated", "user_id", "generated_at"),
    )

    # ── Primary key ──────────────────────────────────────────────────────────
    id_report: uuid.UUID = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Unique report identifier (UUID v4).",
    )

    # ── Foreign keys ─────────────────────────────────────────────────────────
    user_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        comment="UUID of the client who owns this report.",
    )
    adjustment_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("measurement_adjustments.id", ondelete="RESTRICT"),
        nullable=False,
        comment="FK to the Module 5 measurement_adjustments record used at generation time.",
    )
    fabric_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("fabrics.fabric_id", ondelete="RESTRICT"),
        nullable=False,
        comment="FK to the fabrics record (Module 3).",
    )
    model_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("models.model_id", ondelete="RESTRICT"),
        nullable=False,
        comment="FK to the garment models record (Module 4).",
    )

    # ── Verdict & advice ──────────────────────────────────────────────────────
    verdict: str = Column(
        String(30),
        nullable=False,
        comment="Compatibility verdict: compatible | incompatible | minor_adjustments",
    )
    advice: str = Column(
        Text,
        nullable=False,
        comment="Textual recommendation from Module 6.",
    )

    # ── JSONB payload columns ─────────────────────────────────────────────────
    adjusted_measurements: dict = Column(
        JSONB,
        nullable=False,
        comment=(
            "Snapshot of Module 5 measurement_adjustments at generation time. "
            "Fields: adjusted_bust_cm, adjusted_waist_cm, adjusted_hips_cm, "
            "bust_ease_cm, waist_ease_cm, hips_ease_cm, ease_source."
        ),
    )
    incompatible_zones: list | None = Column(
        JSONB,
        nullable=True,
        comment=(
            "List of {zone, reason} dicts populated only when verdict='incompatible'. "
            "NULL for compatible or minor_adjustments verdicts."
        ),
    )

    # ── Timestamp ────────────────────────────────────────────────────────────
    generated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="UTC timestamp at report generation. Set server-side; never supplied by caller.",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<RapportMesure id={self.id_report!r} "
            f"user_id={self.user_id!r} verdict={self.verdict!r}>"
        )
