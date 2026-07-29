"""Pydantic schemas for the Measurement_Service (mensuration creation and history)."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


MEASUREMENT_MIN = 0.0
MEASUREMENT_MAX = 300.0


def _validate_measurement(field_name: str, v: float) -> float:
    if v <= MEASUREMENT_MIN:
        raise ValueError(f"{field_name} must be greater than 0 cm.")
    if v > MEASUREMENT_MAX:
        raise ValueError(f"{field_name} must be at most {MEASUREMENT_MAX} cm.")
    return v


class MensurationCreateRequest(BaseModel):
    tour_poitrine:  float = Field(..., description="Chest circumference in cm (0 < x ≤ 300)")
    tour_taille:    float = Field(..., description="Waist circumference in cm (0 < x ≤ 300)")
    tour_hanches:   float = Field(..., description="Hip circumference in cm (0 < x ≤ 300)")
    longueur_bras:  float = Field(..., description="Arm length in cm (0 < x ≤ 300)")
    hauteur:        float = Field(..., description="Height in cm (0 < x ≤ 300)")

    @field_validator("tour_poitrine")
    @classmethod
    def validate_tour_poitrine(cls, v: float) -> float:
        return _validate_measurement("tour_poitrine", v)

    @field_validator("tour_taille")
    @classmethod
    def validate_tour_taille(cls, v: float) -> float:
        return _validate_measurement("tour_taille", v)

    @field_validator("tour_hanches")
    @classmethod
    def validate_tour_hanches(cls, v: float) -> float:
        return _validate_measurement("tour_hanches", v)

    @field_validator("longueur_bras")
    @classmethod
    def validate_longueur_bras(cls, v: float) -> float:
        return _validate_measurement("longueur_bras", v)

    @field_validator("hauteur")
    @classmethod
    def validate_hauteur(cls, v: float) -> float:
        return _validate_measurement("hauteur", v)


class MensurationResponse(BaseModel):
    id_mesure: str
    user_id: str
    tour_poitrine: float
    tour_taille: float
    tour_hanches: float
    longueur_bras: float
    hauteur: float
    date_mensuration: datetime


class MensurationListResponse(BaseModel):
    mensurations: list[MensurationResponse]
    count: int
