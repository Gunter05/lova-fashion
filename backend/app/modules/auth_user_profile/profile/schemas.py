"""Pydantic schemas for the Profile_Service — cni removed, id (UUID) used everywhere."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, EmailStr
from app.modules.auth_user_profile.auth.schemas import UserRole


class UserProfileResponse(BaseModel):
    id: str
    nom: str
    email: str
    role: UserRole
    date_inscription: datetime


class UpdateProfileRequest(BaseModel):
    nom: Optional[str] = Field(None, max_length=100, description="Full name (max 100 chars)")
    email: Optional[EmailStr] = Field(None, description="Valid email address")


class PhotoProfilResponse(BaseModel):
    id_photo: str
    url_photo: str
    date_upload: datetime


class RapportArchiveResponse(BaseModel):
    report_id: str
    date_generation: datetime
    archived_at: datetime


class AdminUserResponse(BaseModel):
    id: str
    nom: str
    email: str
    role: UserRole
    is_active: bool
    date_inscription: datetime


class RoleUpdateRequest(BaseModel):
    role: UserRole
