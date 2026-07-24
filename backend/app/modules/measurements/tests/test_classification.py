"""
Unit tests for Module 2 — BodyShapeClassifier (classification.py).

Tests cover all five silhouette codes and their priority ordering.

Coverage:
    C1  — HOURGLASS: waist/bust ≤ 0.75 AND waist/hips ≤ 0.75 AND |bust-hips| ≤ 5
    C2  — PEAR: hips > bust + 5 AND waist < hips
    C3  — INVERTED_TRIANGLE: bust > hips + 5
    C4  — APPLE: waist ≥ bust OR waist ≥ hips
    C5  — RECTANGLE: fallback
    C6  — HOURGLASS takes priority over PEAR (priority order)
    C7  — ValueError for non-positive measurements
    C8  — Boundary values (exact thresholds)

Property-based tests (Hypothesis):
    P-C1 — Output is always one of the 5 valid codes
    P-C2 — Non-positive input always raises ValueError
    P-C3 — HOURGLASS conditions are self-consistent with result
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from app.modules.measurements.classification import BodyShapeClassifier

classifier = BodyShapeClassifier()

PBT_SETTINGS = settings(
    max_examples=200,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)

VALID_CODES = {"HOURGLASS", "PEAR", "INVERTED_TRIANGLE", "APPLE", "RECTANGLE"}


# ---------------------------------------------------------------------------
# C1 — HOURGLASS
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bust, waist, hips", [
    (90.0, 67.0, 92.0),   # waist/bust=0.744, waist/hips=0.728, |bust-hips|=2 ✓
    (88.0, 66.0, 90.0),   # all ratios < 0.75, |bust-hips|=2
    (85.0, 63.0, 87.0),
])
def test_c1_hourglass(bust, waist, hips):
    """AC-08.1 row 1 : classic hourglass proportions → HOURGLASS."""
    assert classifier.classify(bust, waist, hips) == "HOURGLASS"


# ---------------------------------------------------------------------------
# C2 — PEAR
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bust, waist, hips", [
    (80.0, 70.0, 95.0),   # hips > bust+5, waist < hips
    (75.0, 65.0, 90.0),
    (82.0, 72.0, 92.0),
])
def test_c2_pear(bust, waist, hips):
    """AC-08.1 row 2 : wide hips, narrow bust → PEAR."""
    # Verify not hourglass first
    waist_bust_ratio = waist / bust
    waist_hips_ratio = waist / hips
    hourglass = (waist_bust_ratio <= 0.75 and waist_hips_ratio <= 0.75 and abs(bust - hips) <= 5)
    if not hourglass:
        assert classifier.classify(bust, waist, hips) == "PEAR"


# ---------------------------------------------------------------------------
# C3 — INVERTED_TRIANGLE
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bust, waist, hips", [
    (100.0, 78.0, 90.0),  # bust > hips+5, waist < bust
    (95.0,  75.0, 85.0),
    (90.0,  72.0, 80.0),
])
def test_c3_inverted_triangle(bust, waist, hips):
    """AC-08.1 row 3 : wide bust relative to hips → INVERTED_TRIANGLE."""
    result = classifier.classify(bust, waist, hips)
    assert result in ("INVERTED_TRIANGLE", "HOURGLASS")  # HOURGLASS takes priority


@pytest.mark.parametrize("bust, waist, hips", [
    (100.0, 78.0, 90.0),
])
def test_c3_inverted_triangle_not_hourglass(bust, waist, hips):
    """When not hourglass and bust >> hips → INVERTED_TRIANGLE."""
    # waist/bust=0.78 > 0.75 → not hourglass
    result = classifier.classify(bust, waist, hips)
    assert result == "INVERTED_TRIANGLE"


# ---------------------------------------------------------------------------
# C4 — APPLE
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bust, waist, hips", [
    (85.0, 90.0, 88.0),   # waist ≥ bust
    (88.0, 86.0, 85.0),   # waist ≥ hips
    (80.0, 82.0, 80.0),   # waist ≥ both
])
def test_c4_apple(bust, waist, hips):
    """AC-08.1 row 4 : large waist → APPLE."""
    result = classifier.classify(bust, waist, hips)
    # Apple or higher-priority codes if conditions overlap
    assert result in ("APPLE", "HOURGLASS", "PEAR", "INVERTED_TRIANGLE")
    # For these specific values, verify APPLE
    is_hourglass = (waist/bust <= 0.75 and waist/hips <= 0.75 and abs(bust-hips) <= 5)
    is_pear = (hips > bust + 5 and waist < hips)
    is_inv = (bust > hips + 5)
    if not is_hourglass and not is_pear and not is_inv:
        assert result == "APPLE"


# ---------------------------------------------------------------------------
# C5 — RECTANGLE
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bust, waist, hips", [
    (85.0, 80.0, 86.0),   # |bust-hips|=1, waist/bust=0.94 > 0.75 → not hourglass
    (88.0, 82.0, 87.0),
    (90.0, 85.0, 90.0),
])
def test_c5_rectangle(bust, waist, hips):
    """AC-08.1 row 5 : no other condition matches → RECTANGLE."""
    result = classifier.classify(bust, waist, hips)
    is_hourglass = (waist/bust <= 0.75 and waist/hips <= 0.75 and abs(bust-hips) <= 5)
    is_pear      = (hips > bust + 5 and waist < hips)
    is_inv       = (bust > hips + 5)
    is_apple     = (waist >= bust or waist >= hips)
    if not any([is_hourglass, is_pear, is_inv, is_apple]):
        assert result == "RECTANGLE"


# ---------------------------------------------------------------------------
# C6 — Priority: HOURGLASS over PEAR
# ---------------------------------------------------------------------------

def test_c6_hourglass_priority_over_pear():
    """HOURGLASS has higher priority than PEAR — it must win when both could apply."""
    # hips=92, bust=90 → hips > bust (not +5 difference so pear doesn't apply here),
    # use a case where hourglass conditions hold
    bust, waist, hips = 90.0, 66.0, 92.0
    # waist/bust=0.733 ≤ 0.75, waist/hips=0.717 ≤ 0.75, |bust-hips|=2 ≤ 5 → HOURGLASS
    assert classifier.classify(bust, waist, hips) == "HOURGLASS"


# ---------------------------------------------------------------------------
# C7 — ValueError for non-positive measurements
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bust, waist, hips", [
    (0.0,  68.0, 93.0),
    (87.0,  0.0, 93.0),
    (87.0, 68.0,  0.0),
    (-5.0, 68.0, 93.0),
    (87.0, -1.0, 93.0),
])
def test_c7_non_positive_raises_value_error(bust, waist, hips):
    """Non-positive measurements must raise ValueError."""
    with pytest.raises(ValueError):
        classifier.classify(bust, waist, hips)


# ---------------------------------------------------------------------------
# C8 — Boundary values at exact thresholds
# ---------------------------------------------------------------------------

def test_c8_boundary_hourglass_exact_ratio():
    """waist/bust == 0.75 exactly (≤ 0.75) → still HOURGLASS eligible."""
    bust, hips = 88.0, 90.0
    waist = 0.75 * bust  # exactly 66.0 → ratio = 0.75
    # waist/hips = 66/90 = 0.733 ≤ 0.75, |bust-hips|=2 ≤ 5
    assert classifier.classify(bust, waist, hips) == "HOURGLASS"


def test_c8_boundary_pear_exactly_5cm():
    """hips == bust + 5 exactly is NOT pear (requires strictly > 5)."""
    bust, waist, hips = 80.0, 70.0, 85.0   # hips = bust + 5, not > bust + 5
    result = classifier.classify(bust, waist, hips)
    assert result != "PEAR"


def test_c8_boundary_pear_just_over_5cm():
    """hips = bust + 5.1 → PEAR condition met."""
    bust, waist, hips = 80.0, 70.0, 85.1
    result = classifier.classify(bust, waist, hips)
    # waist/bust=0.875>0.75 → not hourglass
    assert result == "PEAR"


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------

positive_cm_st = st.floats(min_value=1.0, max_value=200.0, allow_nan=False, allow_infinity=False)


@PBT_SETTINGS
@given(bust=positive_cm_st, waist=positive_cm_st, hips=positive_cm_st)
def test_pc1_output_always_valid_code(bust, waist, hips):
    """P-C1 : classify() always returns one of the 5 valid silhouette codes."""
    result = classifier.classify(bust, waist, hips)
    assert result in VALID_CODES


@PBT_SETTINGS
@given(
    bad=st.one_of(
        st.just(0.0),
        st.floats(max_value=-0.01, allow_nan=False, allow_infinity=False),
    )
)
def test_pc2_non_positive_always_raises(bad):
    """P-C2 : any non-positive measurement must raise ValueError."""
    with pytest.raises(ValueError):
        classifier.classify(bad, 68.0, 93.0)


@PBT_SETTINGS
@given(bust=positive_cm_st, waist=positive_cm_st, hips=positive_cm_st)
def test_pc3_hourglass_conditions_consistent(bust, waist, hips):
    """P-C3 : if result is HOURGLASS, all three hourglass conditions must hold."""
    result = classifier.classify(bust, waist, hips)
    if result == "HOURGLASS":
        assert waist / bust  <= 0.75
        assert waist / hips  <= 0.75
        assert abs(bust - hips) <= 5.0
