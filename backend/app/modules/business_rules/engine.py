"""
Ease Allowance Calculation Engine for Module 5.
Tasks T-03.1 – T-03.4 — AC-02.1–02.4, AC-03.1, AC-04.1–04.2, Design §6

Pure arithmetic — zero database access.
All inputs and outputs are plain Python floats/strings; no ORM types here.

Public surface
--------------
EaseInput       dataclass — inputs to compute()
ZoneResult      dataclass — per-zone output (raw, ease, adjusted)
EaseOutput      dataclass — full result from compute()
EaseEngine      class     — call .compute(EaseInput) → EaseOutput

Private helpers (tested independently)
_resolve_delta(category)     → (delta_cm, ease_source)   T-03.1
_compute_zone(raw, delta)    → (adjusted_cm, warnings)   T-03.2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# T-03.1 — Constants and delta resolution
# ---------------------------------------------------------------------------

# Canonical ease rules (mirrors ease_rules table seeded by migration 005).
# Keyed by elasticity_category value from fabric_categories.reference_rigidity_level.
_EASE_RULES: dict[str, float] = {
    "rigid":        4.0,   # AC-02.1 — non-elastic fabrics (e.g. Pagne Wax)
    "semi-stretch": 2.0,   # AC-02.2 — lightly elastic fabrics
    "stretch":     -2.0,   # AC-02.3 — highly elastic fabrics (e.g. Jersey)
}

# Default ease applied when the elasticity category is absent or unknown (AC-02.4)
_DEFAULT_EASE_CM: float = 3.0

# Hard arithmetic floor — adjusted value is never allowed below this (AC-04.1)
_FLOOR_CM: float = 0.0

# Soft warning threshold — values above floor but below this indicate suspect CV data (AC-04.2)
_WARN_CM: float = 30.0


def _resolve_delta(
    elasticity_category: str | None,
) -> tuple[float, Literal["rule", "default_fallback"]]:
    """
    Map an elasticity category to (delta_cm, ease_source).

    Returns
    -------
    delta_cm    : float — cm to add (positive) or subtract (negative) from raw measurement.
    ease_source : "rule"             — delta found in _EASE_RULES.
                  "default_fallback" — unknown/None category; _DEFAULT_EASE_CM applied.

    AC-02.1 – AC-02.4 · Design §6.2
    """
    if elasticity_category in _EASE_RULES:
        return _EASE_RULES[elasticity_category], "rule"
    return _DEFAULT_EASE_CM, "default_fallback"


# ---------------------------------------------------------------------------
# T-03.2 — Per-zone calculation with floor clamp + warnings
# ---------------------------------------------------------------------------

def _compute_zone(raw: float, delta: float) -> tuple[float, list[str]]:
    """
    Apply ease delta to a single measurement zone.

    Processing order:
        1. adjusted = raw + delta
        2. If adjusted < _FLOOR_CM → clamp to 0.0, emit floor warning   (AC-04.1)
        3. Elif adjusted < _WARN_CM  → emit suspect-data warning         (AC-04.2)
        4. Round to 1 decimal place                                      (NFR-04)

    Returns
    -------
    (adjusted_cm, warnings)
        adjusted_cm : float — final value, clamped and rounded.
        warnings    : list[str] — human-readable warning messages (may be empty).

    Design §6.3
    """
    adjusted = raw + delta
    warnings: list[str] = []

    if adjusted < _FLOOR_CM:
        warnings.append(
            f"Valeur ajustée ({adjusted:.1f} cm) < 0 cm — plafonnée à 0.0 cm."
        )
        adjusted = _FLOOR_CM
    elif adjusted < _WARN_CM:
        warnings.append(
            f"Valeur ajustée ({adjusted:.1f} cm) < 30 cm — données d'entrée suspectes."
        )

    return round(adjusted, 1), warnings


# ---------------------------------------------------------------------------
# T-03.3 — Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class EaseInput:
    """
    Inputs to EaseEngine.compute().
    Design §6.1
    """
    bust_cm: float
    waist_cm: float
    hips_cm: float
    elasticity_category: str | None   # None → triggers default fallback (AC-02.4)


@dataclass
class ZoneResult:
    """
    Calculation detail for one measurement zone.
    Stored individually in MeasurementAdjustment for per-zone auditability (AC-03.1).
    Design §6.1
    """
    raw_cm: float
    ease_cm: float
    adjusted_cm: float


@dataclass
class EaseOutput:
    """
    Full output from EaseEngine.compute().
    Design §6.1
    """
    bust: ZoneResult
    waist: ZoneResult
    hips: ZoneResult
    ease_source: Literal["rule", "default_fallback"]
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# T-03.4 — EaseEngine: orchestrates resolution + per-zone computation
# ---------------------------------------------------------------------------

class EaseEngine:
    """
    Stateless ease allowance calculator.
    Instantiate once and reuse across requests.

    Usage
    -----
        engine = EaseEngine()
        output = engine.compute(EaseInput(
            bust_cm=87.5, waist_cm=68.0, hips_cm=93.0,
            elasticity_category="rigid",
        ))
        # output.bust.adjusted_cm == 91.5
        # output.ease_source      == "rule"
        # output.warnings         == []

    Design §6.4
    """

    def compute(self, inp: EaseInput) -> EaseOutput:
        """
        Compute ease-adjusted measurements for all three zones.

        Steps:
            1. Resolve delta and ease_source from elasticity_category  (T-03.1)
            2. Compute each zone with floor clamp + warnings            (T-03.2)
            3. Append fallback warning when ease_source == 'default_fallback' (AC-02.4)
            4. Return EaseOutput

        Parameters
        ----------
        inp : EaseInput — raw measurements + elasticity category.

        Returns
        -------
        EaseOutput — zone results, ease_source, and any warning messages.
        """
        # Step 1 — resolve delta
        delta, ease_source = _resolve_delta(inp.elasticity_category)

        all_warnings: list[str] = []

        # Step 2 — compute all three zones
        bust_adj,  bust_w  = _compute_zone(inp.bust_cm,  delta)
        waist_adj, waist_w = _compute_zone(inp.waist_cm, delta)
        hips_adj,  hips_w  = _compute_zone(inp.hips_cm,  delta)

        all_warnings.extend(bust_w)
        all_warnings.extend(waist_w)
        all_warnings.extend(hips_w)

        # Step 3 — fallback warning (AC-02.4)
        if ease_source == "default_fallback":
            all_warnings.append(
                f"Catégorie d'élasticité inconnue ({inp.elasticity_category!r}) — "
                f"aisance par défaut +{_DEFAULT_EASE_CM:.0f} cm appliquée."
            )

        # Step 4 — build and return output
        return EaseOutput(
            bust=ZoneResult(
                raw_cm=round(inp.bust_cm, 1),
                ease_cm=round(delta, 1),
                adjusted_cm=bust_adj,
            ),
            waist=ZoneResult(
                raw_cm=round(inp.waist_cm, 1),
                ease_cm=round(delta, 1),
                adjusted_cm=waist_adj,
            ),
            hips=ZoneResult(
                raw_cm=round(inp.hips_cm, 1),
                ease_cm=round(delta, 1),
                adjusted_cm=hips_adj,
            ),
            ease_source=ease_source,
            warnings=all_warnings,
        )
