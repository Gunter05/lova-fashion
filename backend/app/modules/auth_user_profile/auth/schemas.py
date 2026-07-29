"""Pydantic schemas for the Auth_Service (registration, login, logout, error responses)."""
from __future__ import annotations
import re
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, EmailStr


class UserRole(str, Enum):
    CLIENT = "Client"
    TAILOR = "Tailor"
    ADMIN = "Admin"




CNI_REGEX = re.compile(r'^[A-Za-z0-9]{9}$')


class RegisterRequest(BaseModel):
    cni: str = Field(..., description="National Identity Card — exactly 9 alphanumeric characters")
    nom: str = Field(..., max_length=100, description="Full name")
    email: EmailStr
    mot_de_passe: str = Field(..., min_length=8, description="Password (min 8 characters)")
    role: UserRole

    @field_validator("cni")
    @classmethod
    def validate_cni(cls, v: str) -> str:
        if not CNI_REGEX.match(v):
            raise ValueError("CNI must be exactly 9 alphanumeric characters.")
        return v


class RegisterResponse(BaseModel):
    cni: str
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
