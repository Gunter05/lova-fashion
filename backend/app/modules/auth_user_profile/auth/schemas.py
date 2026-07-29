"""Pydantic schemas for the Auth_Service — no cni field anywhere."""
from __future__ import annotations

import uuid as _uuid_module
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr


class UserRole(str, Enum):
    CLIENT = "Client"
    TAILOR = "Tailor"
    ADMIN = "Admin"


class RegisterRequest(BaseModel):
    nom: str = Field(..., max_length=100, description="Full name")
    email: EmailStr
    mot_de_passe: str = Field(..., min_length=8, description="Password (min 8 characters)")


class RegisterResponse(BaseModel):
    id: str
    nom: str
    email: str
    role: UserRole
    date_inscription: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    mot_de_passe: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class FieldError(BaseModel):
    field: str | None = None
    message: str


class ErrorResponse(BaseModel):
    error: str
    field: str | None = None
    message: str


class MultiFieldErrorResponse(BaseModel):
    error: str = "VALIDATION_ERROR"
    field: str | None = None
    message: str = "Multiple validation errors."
    details: list[FieldError] = []
