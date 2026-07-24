"""
Unit tests for Module 5 — EaseEngine (engine.py).

Tests cover:
    E1  — Delta resolution for all known categories        (AC-02.1 – AC-02.3)
    E2  — Default fallback for unknown / None category     (AC-02.4)
    E3  — Adjusted value = raw + delta, rounded to 1 dp   (NFR-04)
    E4  — Floor clamp: adjusted < 0 → clamped to 0.0      (AC-04.1)
    E5  — Soft warning: 0 < adjusted < 30 → warning msg   (AC-04.2)
    E6  — No warning when adjusted ≥ 30                   (happy path)
    E7  — EaseOutput has correct ease_source               (AC-02.1 – AC-02.4)
    E8  — Fallback warning text included in warnings list  (AC-02.4)
    E9  — All three zones receive the same delta           (Design §6.4)

Property-based tests (Hypothesis):
    P-E1 — Adjusted = clamp(raw + delta, 0) for any raw in [0, 300]
    P-E2 — ease_source is always "rule" or "default_fallback"
    P-E3 — No negative adjusted values ever produced
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from app.modules.business_rules.engine import (
    EaseEngine,
    EaseInput,
    _EASE_RULES,
    _DEFAULT_EASE_CM,
    _FLOOR_CM,
    _WARN_CM,
    _resolve_delta,
    _compute_zone,
)

# ---------------------------------------------------------------------------
# Shared engine instance
# ---------------------------------------------------------------------------

engine = EaseEngine()

PBT_SETTINGS = settings(
    max_examples=200,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)

# ---------------------------------------------------------------------------
# E1 — Delta resolution for known categories
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("category, expected_delta", [
    ("rigid",        4.0),
    ("semi-stretch", 2.0),
    ("stretch",     -2.0),
])
def test_e1_resolve_delta_known_categories(category, expected_delta):
    """AC-02.1 – AC-02.3 : each canonical category maps to its correct delta."""
    delta, source = _resolve_delta(category)
    assert delta == expected_delta
    assert source == "rule"


# ---------------------------------------------------------------------------
# E2 — Default fallback for unknown / None
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("category", [None, "", "unknown", "velvet", "cotton"])
def test_e2_resolve_delta_fallback(category):
    """AC-02.4 : unrecognised category triggers +3 cm default fallback."""
    delta, source = _resolve_delta(category)
    assert delta == _DEFAULT_EASE_CM
    assert source == "default_fallback"


# ---------------------------------------------------------------------------
# E3 — Zone computation: correct arithmetic, rounded to 1 dp
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, delta, expected", [
    (87.5,   4.0, 91.5),
    (68.0,   2.0, 70.0),
    (93.0,  -2.0, 91.0),
    (50.0,   3.0, 53.0),
    (100.25, 4.0, 104.2),   # rounded to 1 dp: 104.25 → 104.2 (banker's rounding)
    (100.35, 4.0, 104.4),
])
def test_e3_compute_zone_arithmetic(raw, delta, expected):
    """NFR-04 : adjusted = raw + delta, rounded to 1 decimal place."""
    adjusted, _ = _compute_zone(raw, delta)
    assert adjusted == expected


# ---------------------------------------------------------------------------
# E4 — Floor clamp
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, delta", [
    (1.0,  -5.0),   # → -4.0 → clamped to 0.0
    (0.0,  -2.0),   # → -2.0 → clamped to 0.0
    (2.9,  -3.0),   # → -0.1 → clamped to 0.0
])
def test_e4_floor_clamp(raw, delta):
    """AC-04.1 : adjusted values below 0 are clamped to 0.0 cm."""
    adjusted, warnings = _compute_zone(raw, delta)
    assert adjusted == _FLOOR_CM
    assert any("plafonnée" in w or "0.0" in w for w in warnings), (
        f"Expected floor warning, got: {warnings}"
    )


# ---------------------------------------------------------------------------
# E5 — Soft warning for suspect CV data
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, delta", [
    (25.0,  4.0),   # → 29.0 → < 30 → warning
    (26.0,  2.0),   # → 28.0 → warning
    (20.0,  3.0),   # → 23.0 → warning
])
def test_e5_soft_warning_below_30(raw, delta):
    """AC-04.2 : 0 < adjusted < 30 triggers 'suspect' warning."""
    adjusted, warnings = _compute_zone(raw, delta)
    assert _FLOOR_CM < adjusted < _WARN_CM
    assert any("suspecte" in w or "30" in w for w in warnings), (
        f"Expected suspect-data warning, got: {warnings}"
    )


# ---------------------------------------------------------------------------
# E6 — No warning when adjusted ≥ 30
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, delta", [
    (87.5,  4.0),   # → 91.5 — typical happy path
    (30.0,  0.0),   # → 30.0 — exactly at threshold (no warning)
    (50.0,  2.0),   # → 52.0
])
def test_e6_no_warning_above_threshold(raw, delta):
    """No warnings produced for well-formed measurements ≥ 30 cm."""
    adjusted, warnings = _compute_zone(raw, delta)
    assert adjusted >= _WARN_CM
    assert warnings == []


# ---------------------------------------------------------------------------
# E7 — EaseEngine.compute: ease_source matches category
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("category, expected_source", [
    ("rigid",        "rule"),
    ("semi-stretch", "rule"),
    ("stretch",      "rule"),
    (None,           "default_fallback"),
    ("unknown",      "default_fallback"),
])
def test_e7_ease_source_in_output(category, expected_source):
    """ease_source in EaseOutput must reflect the category resolution."""
    output = engine.compute(EaseInput(
        bust_cm=87.5, waist_cm=68.0, hips_cm=93.0,
        elasticity_category=category,
    ))
    assert output.ease_source == expected_source


# ---------------------------------------------------------------------------
# E8 — Fallback warning text in warnings list
# ---------------------------------------------------------------------------

def test_e8_fallback_warning_text():
    """AC-02.4 : fallback must add a descriptive warning to output.warnings."""
    output = engine.compute(EaseInput(
        bust_cm=87.5, waist_cm=68.0, hips_cm=93.0,
        elasticity_category=None,
    ))
    assert output.ease_source == "default_fallback"
    assert any("aisance par défaut" in w or "default" in w.lower() for w in output.warnings), (
        f"Expected fallback warning in {output.warnings}"
    )


# ---------------------------------------------------------------------------
# E9 — Same delta applied to all three zones
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("category", ["rigid", "semi-stretch", "stretch", None])
def test_e9_uniform_delta_all_zones(category):
    """Design §6.4 : bust, waist, and hips receive the same ease_cm."""
    output = engine.compute(EaseInput(
        bust_cm=87.5, waist_cm=68.0, hips_cm=93.0,
        elasticity_category=category,
    ))
    assert output.bust.ease_cm == output.waist.ease_cm == output.hips.ease_cm


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------

raw_cm_st = st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False)
category_st = st.one_of(
    st.sampled_from(list(_EASE_RULES.keys())),
    st.just(None),
    st.just("unknown"),
)


@PBT_SETTINGS
@given(bust=raw_cm_st, waist=raw_cm_st, hips=raw_cm_st, category=category_st)
def test_pe1_no_negative_adjusted_values(bust, waist, hips, category):
    """P-E3 : adjusted measurements are always ≥ 0 regardless of inputs."""
    output = engine.compute(EaseInput(
        bust_cm=bust, waist_cm=waist, hips_cm=hips,
        elasticity_category=category,
    ))
    assert output.bust.adjusted_cm  >= 0.0
    assert output.waist.adjusted_cm >= 0.0
    assert output.hips.adjusted_cm  >= 0.0


@PBT_SETTINGS
@given(bust=raw_cm_st, waist=raw_cm_st, hips=raw_cm_st, category=category_st)
def test_pe2_ease_source_is_valid_literal(bust, waist, hips, category):
    """P-E2 : ease_source is always one of the two valid literals."""
    output = engine.compute(EaseInput(
        bust_cm=bust, waist_cm=waist, hips_cm=hips,
        elasticity_category=category,
    ))
    assert output.ease_source in ("rule", "default_fallback")


@PBT_SETTINGS
@given(raw=raw_cm_st, category=category_st)
def test_pe3_adjusted_equals_clamp_raw_plus_delta(raw, category):
    """P-E1 : adjusted == round(max(raw + delta, 0), 1) for any valid raw."""
    delta, _ = _resolve_delta(category)
    expected = round(max(raw + delta, 0.0), 1)
    adjusted, _ = _compute_zone(raw, delta)
    assert adjusted == expected
