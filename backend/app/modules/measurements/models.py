"""
SQLAlchemy ORM models for Module 2 — Photo Capture & Measurement Estimation.
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
    pass


class BodyShape(Base):
    """
    Reference table — the five recognised body silhouette classifications.
    Seeded by migration 001. Never modified at runtime.
    """

    __tablename__ = "body_shapes"

    code: str = Column(String(30), primary_key=True)
    name: str = Column(String(100), nullable=False)
    description: str | None = Column(Text, nullable=True)

    # Reverse relationship (informational)
    measurements: list["RawMeasurement"] = relationship(
        "RawMeasurement", back_populates="body_shape"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BodyShape code={self.code!r}>"


class CaptureSession(Base):
    """
    One row per measurement capture attempt.
    Lifecycle: empty → processing → success | failed.
    Task T-02.1 — Design §3.1
    """

    __tablename__ = "capture_sessions"

    __table_args__ = (
        CheckConstraint(
            "status IN ('empty', 'processing', 'success', 'failed')",
            name="ck_capture_sessions_status",
        ),
        CheckConstraint(
            "entered_stature IS NULL OR (entered_stature >= 100 AND entered_stature <= 250)",
            name="ck_capture_sessions_stature_range",
        ),
        # Partial unique index enforced in the DB migration;
        # declared here for documentation only — SQLAlchemy does not
        # enforce partial unique constraints at the ORM level.
    )

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: uuid.UUID = Column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    status: str = Column(String(20), nullable=False, default="empty")
    front_photo_url: str | None = Column(Text, nullable=True)
    profile_photo_url: str | None = Column(Text, nullable=True)
    entered_stature: Decimal | None = Column(Numeric(5, 1), nullable=True)
    is_active: bool = Column(Boolean, nullable=False, default=False)
    retry_count: int = Column(Integer, nullable=False, default=0)
    failure_reason: str | None = Column(Text, nullable=True)
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # One-to-one: each successful session produces exactly one raw measurement
    measurement: "RawMeasurement | None" = relationship(
        "RawMeasurement",
        back_populates="session",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CaptureSession id={self.id!r} status={self.status!r}>"


class RawMeasurement(Base):
    """
    Anatomical measurements produced by the CV pipeline for one capture session.
    Task T-02.2 — Design §3.2
    """

    __tablename__ = "raw_measurements"

    __table_args__ = (
        UniqueConstraint("session_id", name="uq_raw_measurements_session_id"),
    )

    id: uuid.UUID = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: uuid.UUID = Column(
        UUID(as_uuid=True),
        ForeignKey("capture_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    bust_cm: Decimal = Column(Numeric(5, 1), nullable=False)
    waist_cm: Decimal = Column(Numeric(5, 1), nullable=False)
    hips_cm: Decimal = Column(Numeric(5, 1), nullable=False)
    silhouette_code: str = Column(
        String(30),
        ForeignKey("body_shapes.code"),
        nullable=False,
    )
    created_at: datetime = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    session: CaptureSession = relationship(
        "CaptureSession", back_populates="measurement"
    )
    body_shape: BodyShape = relationship(
        "BodyShape", back_populates="measurements"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<RawMeasurement session_id={self.session_id!r} "
            f"bust={self.bust_cm} waist={self.waist_cm} hips={self.hips_cm}>"
        )
