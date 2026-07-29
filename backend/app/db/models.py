"""
SQLAlchemy ORM models — users table uses id (UUID) as primary key.
cni has been removed entirely.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.modules.auth_user_profile.auth.schemas import UserRole


class UserModel(Base):
    """Maps to the `users` table. Primary key is id (UUID)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    nom: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    mot_de_passe: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(
            UserRole,
            name="user_role",
            values_callable=lambda x: [e.value for e in x],
            create_constraint=True,
        ),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    date_inscription: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    photos: Mapped[list["PhotoProfilModel"]] = relationship(
        "PhotoProfilModel", back_populates="user", cascade="all, delete-orphan"
    )
    mensurations: Mapped[list["MensurationModel"]] = relationship(
        "MensurationModel", back_populates="user", cascade="all, delete-orphan"
    )
    rapport_archives: Mapped[list["RapportArchiveModel"]] = relationship(
        "RapportArchiveModel", back_populates="user", cascade="all, delete-orphan"
    )


class PhotoProfilModel(Base):
    """Maps to the `photo_profil` table."""

    __tablename__ = "photo_profil"

    id_photo: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    url_photo: Mapped[str] = mapped_column(Text, nullable=False)
    date_upload: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="photos")


class MensurationModel(Base):
    """Maps to the `mensuration` table."""

    __tablename__ = "mensuration"

    id_mesure: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    tour_poitrine: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    tour_taille:   Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    tour_hanches:  Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    longueur_bras: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    hauteur:       Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    date_mensuration: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    source_event_hash: Mapped[Optional[str]] = mapped_column(Text, unique=True, nullable=True)

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="mensurations")


class RapportArchiveModel(Base):
    """Maps to the `rapport_archive` table."""

    __tablename__ = "rapport_archive"
    __table_args__ = (
        UniqueConstraint("user_id", "report_id", name="uq_rapport_user_report_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    report_id: Mapped[str] = mapped_column(Text, nullable=False)
    date_generation: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archived_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="rapport_archives")


class TokenDenylistModel(Base):
    """Maps to the `token_denylist` table."""

    __tablename__ = "token_denylist"

    jti: Mapped[str] = mapped_column(Text, primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TailorClientAssignmentModel(Base):
    """Maps to the `tailor_client_assignment` table."""

    __tablename__ = "tailor_client_assignment"
    __table_args__ = ({},)

    tailor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
