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
    (100.35, 4.0, 104.3),   # 100.35 + 4.0 = 104.35 → 104.3 (IEEE 754: stored as < 104.35)
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


# ===========================================================================
# Module 6 — RuleEvaluator deterministic unit tests (RE-01 – RE-10)
# ===========================================================================

import uuid as _uuid

from app.modules.business_rules.engine import (
    RuleEvaluator,
    RuleInput,
    RuleRecord,
    RiskZoneDict,
)

# ---------------------------------------------------------------------------
# Shared evaluator instance
# ---------------------------------------------------------------------------

evaluator = RuleEvaluator()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_rule(
    *,
    zone_name: str = "bust",
    condition: str = "value > 90.0",
    severity: str = "Incompatible",
    explanation: str | None = "Explication standard.",
    version: int = 1,
    zone_id: _uuid.UUID | None = None,
) -> RuleRecord:
    return RuleRecord(
        rule_id=_uuid.uuid4(),
        zone_id=zone_id or _uuid.uuid4(),
        zone_name=zone_name,
        mathematical_condition=condition,
        severity_level=severity,
        explanation_message=explanation,
        version=version,
    )


def _make_input(
    rules: list[RuleRecord],
    measurements: dict[str, float] | None = None,
    critical_zone_ids: list[_uuid.UUID] | None = None,
) -> RuleInput:
    return RuleInput(
        rules=rules,
        zone_measurements=measurements or {"bust": 91.5, "waist": 70.0, "hips": 95.0},
        critical_zone_ids=critical_zone_ids or [],
    )


# ---------------------------------------------------------------------------
# RE-01 — Empty rules list → []
# ---------------------------------------------------------------------------

def test_re01_empty_rules_returns_empty_list():
    """RE-01: evaluate() with no rules always returns an empty list."""
    result = evaluator.evaluate(_make_input(rules=[]))
    assert result == []


# ---------------------------------------------------------------------------
# RE-02 — Single matching rule fires → 1 RiskZoneDict item
# ---------------------------------------------------------------------------

def test_re02_single_matching_rule_fires():
    """RE-02: one rule whose condition is satisfied → list with exactly 1 item."""
    rule = _make_rule(zone_name="bust", condition="value > 90.0", severity="Incompatible")
    result = evaluator.evaluate(_make_input(rules=[rule], measurements={"bust": 95.0}))
    assert len(result) == 1
    assert isinstance(result[0], RiskZoneDict)


# ---------------------------------------------------------------------------
# RE-03 — Rule does not fire (condition false) → []
# ---------------------------------------------------------------------------

def test_re03_rule_does_not_fire():
    """RE-03: rule condition evaluates to False → empty output list."""
    rule = _make_rule(zone_name="bust", condition="value > 100.0")
    result = evaluator.evaluate(_make_input(rules=[rule], measurements={"bust": 91.5}))
    assert result == []


# ---------------------------------------------------------------------------
# RE-04 — Two rules fire for different zones → 2 items
# ---------------------------------------------------------------------------

def test_re04_two_rules_two_zones():
    """RE-04: two rules, each for a distinct zone, both fire → 2 RiskZoneDict items."""
    rule_bust = _make_rule(zone_name="bust",  condition="value > 90.0", severity="Incompatible")
    rule_hips = _make_rule(zone_name="hips",  condition="value > 90.0", severity="Reserve")
    result = evaluator.evaluate(_make_input(
        rules=[rule_bust, rule_hips],
        measurements={"bust": 95.0, "hips": 100.0},
    ))
    assert len(result) == 2


# ---------------------------------------------------------------------------
# RE-05 — Severity "Incompatible" propagated to localized_verdict
# ---------------------------------------------------------------------------

def test_re05_severity_incompatible_propagated():
    """RE-05: severity_level 'Incompatible' is copied verbatim to localized_verdict."""
    rule = _make_rule(severity="Incompatible", condition="value > 0.0")
    result = evaluator.evaluate(_make_input(rules=[rule], measurements={"bust": 50.0}))
    assert len(result) == 1
    assert result[0].localized_verdict == "Incompatible"


# ---------------------------------------------------------------------------
# RE-06 — Severity "Reserve" propagated to localized_verdict
# ---------------------------------------------------------------------------

def test_re06_severity_reserve_propagated():
    """RE-06: severity_level 'Reserve' is copied verbatim to localized_verdict."""
    rule = _make_rule(severity="Reserve", condition="value > 0.0")
    result = evaluator.evaluate(_make_input(rules=[rule], measurements={"bust": 50.0}))
    assert len(result) == 1
    assert result[0].localized_verdict == "Reserve"


# ---------------------------------------------------------------------------
# RE-07 — Null explanation_message triggers fallback (non-empty) explanation
# ---------------------------------------------------------------------------

def test_re07_null_explanation_triggers_fallback():
    """RE-07: when explanation_message is None, a non-empty fallback string is produced."""
    rule = _make_rule(explanation=None, condition="value > 0.0")
    result = evaluator.evaluate(_make_input(rules=[rule], measurements={"bust": 50.0}))
    assert len(result) == 1
    assert len(result[0].explanation.strip()) > 0


# ---------------------------------------------------------------------------
# RE-08 — Malformed condition string is skipped; no exception raised
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_condition", [
    # Syntax errors — cannot be parsed as a valid expression
    "import os",
    "!!!",
    "value >",
    "@ # $",
    # Undefined variable — simpleeval raises NameNotDefined
    "value > undefined_var",
    "undefined_var + 1 > 0",
])
def test_re08_malformed_condition_skipped_no_exception(bad_condition):
    """RE-08: a malformed mathematical_condition is silently skipped; evaluate() must
    not raise and the resulting list must not contain an item for that rule."""
    rule = _make_rule(condition=bad_condition)
    # Should never raise
    result = evaluator.evaluate(_make_input(rules=[rule], measurements={"bust": 95.0}))
    # The bad rule must be excluded from output
    assert result == []


# ---------------------------------------------------------------------------
# RE-09 — Unknown zone_name (not in zone_measurements) is skipped
# ---------------------------------------------------------------------------

def test_re09_unknown_zone_name_skipped():
    """RE-09: a rule whose zone_name is absent from zone_measurements is skipped;
    no exception, and the rule is not present in the output."""
    rule = _make_rule(zone_name="neck", condition="value > 30.0")
    # zone_measurements has no "neck" key
    result = evaluator.evaluate(_make_input(
        rules=[rule],
        measurements={"bust": 91.5, "waist": 70.0, "hips": 95.0},
    ))
    assert result == []


# ---------------------------------------------------------------------------
# RE-10 — rule_version copied verbatim from RuleRecord.version
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("version", [1, 3, 42])
def test_re10_rule_version_copied_to_output(version):
    """RE-10: rule_version in RiskZoneDict matches the version field of the source
    RuleRecord exactly."""
    rule = _make_rule(version=version, condition="value > 0.0")
    result = evaluator.evaluate(_make_input(rules=[rule], measurements={"bust": 50.0}))
    assert len(result) == 1
    assert result[0].rule_version == version


# ===========================================================================
# Module 6 — Property-Based Tests (Hypothesis)
# ===========================================================================
#
# **Validates: Requirements 3.9, 8.3**
#
# Property 1: Determinism — same inputs always produce an identical
# list[RiskZoneDict] on every call to RuleEvaluator.evaluate().
# ===========================================================================

import uuid as _uuid_pbt

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Shared Hypothesis settings for Module 6 PBT
# ---------------------------------------------------------------------------

M6_PBT_SETTINGS = settings(
    max_examples=200,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# zone_measurements: dict with exactly the three canonical keys, float values ≥ 0.0
zone_measurements_st = st.fixed_dictionaries({
    "bust":  st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
    "waist": st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
    "hips":  st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
})

# severity: one of the two valid severity_level literals
severity_st = st.sampled_from(["Incompatible", "Reserve"])


# ---------------------------------------------------------------------------
# Property 1: Determinism (Requirements 3.9, 8.3)
# ---------------------------------------------------------------------------

@M6_PBT_SETTINGS
@given(zone_measurements=zone_measurements_st, severity=severity_st)
def test_p1_determinism(zone_measurements: dict, severity: str) -> None:
    """
    **Validates: Requirements 3.9, 8.3**

    Property 1 — Determinism:
    For any well-formed zone_measurements dict and severity value, calling
    RuleEvaluator().evaluate() twice with identical inputs must return
    exactly the same list[RiskZoneDict] both times.

    Two rule variants are included so that both the "condition fires" and
    "condition never fires" code paths are exercised across the generated
    inputs:
      - rule_always fires when value > 0.0  (fires for any measurement > 0)
      - rule_never  fires when value > 999999.0  (never fires in practice)
    """
    _evaluator = RuleEvaluator()
    shared_zone_id = _uuid_pbt.uuid4()

    rules = [
        RuleRecord(
            rule_id=_uuid_pbt.uuid4(),
            zone_id=shared_zone_id,
            zone_name="bust",
            mathematical_condition="value > 0.0",
            severity_level=severity,
            explanation_message="Condition always-fire pour test déterminisme.",
            version=1,
        ),
        RuleRecord(
            rule_id=_uuid_pbt.uuid4(),
            zone_id=shared_zone_id,
            zone_name="waist",
            mathematical_condition="value > 999999.0",
            severity_level=severity,
            explanation_message="Condition never-fire pour test déterminisme.",
            version=1,
        ),
    ]

    inp = RuleInput(
        rules=rules,
        zone_measurements=zone_measurements,
        critical_zone_ids=[shared_zone_id],
    )

    result_1 = _evaluator.evaluate(inp)
    result_2 = _evaluator.evaluate(inp)

    assert result_1 == result_2, (
        f"RuleEvaluator is non-deterministic: first call returned {result_1!r}, "
        f"second call returned {result_2!r} for the same input."
    )


# ===========================================================================
# Module 6 — RuleEvaluator property-based tests (Hypothesis)
# ===========================================================================

# ---------------------------------------------------------------------------
# Shared Hypothesis strategies for Module 6 PBTs
# ---------------------------------------------------------------------------

zone_measurements = st.fixed_dictionaries({
    "bust":  st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
    "waist": st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
    "hips":  st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
})

MODULE6_PBT_SETTINGS = settings(
    max_examples=200,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)

# ---------------------------------------------------------------------------
# P3 — Empty rules list always returns []
# Validates: Requirement 8.1
# ---------------------------------------------------------------------------

@MODULE6_PBT_SETTINGS
@given(measurements=zone_measurements)
def test_p3_empty_rules_returns_empty(measurements):
    """
    **Validates: Requirement 8.1**

    Property 3 — Empty rules → empty output:
    For any zone_measurements dict, an empty rules list always returns [].
    """
    inp = RuleInput(
        rules=[],
        zone_measurements=measurements,
        critical_zone_ids=[],
    )
    result = RuleEvaluator().evaluate(inp)
    assert result == []


# ===========================================================================
# Module 6 — Property-Based Tests: Property 2 (Task 11.3)
# ===========================================================================
#
# **Validates: Requirements 3.4, 3.5**
#
# Property 2: Verdict closure
#   For any zone_measurements dict with floats ≥ 0.0 and any severity drawn
#   from {"Incompatible", "Reserve"}, every RiskZoneDict returned by
#   RuleEvaluator.evaluate() must have localized_verdict ∈
#   {"Incompatible", "Reserve"}.  The engine must never produce an out-of-set
#   verdict value regardless of how many rules fire or which severity is chosen.

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

_VALID_VERDICTS = {"Incompatible", "Reserve"}

# Strategy: dict with keys "bust", "waist", "hips" mapped to floats ≥ 0.0
_zone_measurements_st = st.fixed_dictionaries(
    {
        "bust":  st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
        "waist": st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
        "hips":  st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
    }
)

_PBT2_SETTINGS = settings(
    max_examples=200,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)


@_PBT2_SETTINGS
@given(
    zone_measurements=_zone_measurements_st,
    severity=st.sampled_from(["Incompatible", "Reserve"]),
)
def test_p2_verdict_values_constrained(zone_measurements, severity):
    """
    Property 2: Verdict closure — all localized_verdict values ∈
    {"Incompatible", "Reserve"}.

    Uses a rule with condition "value >= 0.0" so it always fires for any
    measurement ≥ 0.0, guaranteeing the output list is non-empty and that
    every produced RiskZoneDict is subject to the closure check.

    **Validates: Requirements 3.4, 3.5**
    """
    # Build one always-firing rule per zone so the output is never empty.
    rules = [
        _make_rule(
            zone_name=zone_name,
            condition="value >= 0.0",
            severity=severity,
            explanation="Test règle toujours active.",
        )
        for zone_name in zone_measurements
    ]

    inp = _make_input(rules=rules, measurements=zone_measurements)
    result = RuleEvaluator().evaluate(inp)

    # The condition always fires for values ≥ 0.0, so at least one zone must
    # have produced a RiskZoneDict (as long as measurements are ≥ 0.0).
    assert len(result) > 0, (
        f"Expected at least one RiskZoneDict for measurements {zone_measurements}, "
        f"but got an empty list."
    )

    for rz in result:
        assert rz.localized_verdict in _VALID_VERDICTS, (
            f"localized_verdict {rz.localized_verdict!r} is outside the allowed set "
            f"{_VALID_VERDICTS}. Rule severity was {severity!r}."
        )


# ===========================================================================
# Module 6 — Property-Based Tests for RuleEvaluator
# ===========================================================================

# ---------------------------------------------------------------------------
# Shared Hypothesis settings for Module 6 PBT
# ---------------------------------------------------------------------------

M6_PBT_SETTINGS = settings(
    max_examples=200,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)

# Strategy: zone_measurements dict with keys "bust", "waist", "hips" → floats ≥ 0.0
zone_measurements_st = st.fixed_dictionaries({
    "bust":  st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
    "waist": st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
    "hips":  st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
})


# ---------------------------------------------------------------------------
# Property 4: Explanation completeness                    Validates: Req 6.3
#
# Every RiskZoneDict produced for a fired rule has a non-empty explanation,
# even when explanation_message is None (fallback mechanism must kick in).
# ---------------------------------------------------------------------------

@M6_PBT_SETTINGS
@given(zone_measurements=zone_measurements_st)
def test_p4_explanation_never_empty_on_fired_rule(zone_measurements):
    """
    **Validates: Requirements 6.3**

    Property 4 — Explanation completeness:
    For any zone_measurements dict with non-negative floats, a RuleRecord whose
    explanation_message is None and whose condition always fires (value >= 0.0)
    must produce a RiskZoneDict with a non-empty (after strip) explanation.

    This verifies the fallback explanation mechanism (Req 6.3): when
    explanation_message is null/empty, RuleEvaluator builds a non-empty default.
    """
    # Build a rule that always fires (value >= 0.0 is true for all non-negative floats)
    # and has no explanation_message — forcing the fallback path.
    rule = RuleRecord(
        rule_id=_uuid.uuid4(),
        zone_id=_uuid.uuid4(),
        zone_name="bust",
        mathematical_condition="value >= 0.0",
        severity_level="Reserve",
        explanation_message=None,
        version=1,
    )

    inp = RuleInput(
        rules=[rule],
        zone_measurements=zone_measurements,
        critical_zone_ids=[],
    )

    result = RuleEvaluator().evaluate(inp)

    # The rule must have fired (bust is always present and >= 0.0)
    assert len(result) == 1, (
        f"Expected exactly 1 RiskZoneDict (rule always fires), got {len(result)} "
        f"for zone_measurements={zone_measurements}"
    )

    # Core property: explanation must be non-empty after stripping whitespace
    rz = result[0]
    assert len(rz.explanation.strip()) > 0, (
        f"explanation is empty or whitespace-only for rule with "
        f"explanation_message=None; zone_measurements={zone_measurements}"
    )


# ===========================================================================
# Property 8: Malformed condition safety (Requirement 8.4)
#
# **Validates: Requirement 8.4**
#
# Arbitrary condition strings of length 1–200 must never cause an unhandled
# exception from RuleEvaluator.evaluate(). The result may be an empty list
# (malformed condition skipped) or a non-empty list (condition happened to be
# syntactically valid and fired) — the only requirement is: no exception.
# ===========================================================================


@M6_PBT_SETTINGS
@given(
    zone_measurements=zone_measurements_st,
    condition=st.text(min_size=1, max_size=200),
)
def test_p5_malformed_condition_never_raises(
    zone_measurements: dict,
    condition: str,
) -> None:
    """
    **Validates: Requirement 8.4**

    Property 8 — Malformed condition safety:
    For any dict of zone_measurements and any arbitrary string 'condition'
    of length 1–200, calling RuleEvaluator().evaluate() must NEVER raise
    an exception.

    The result is allowed to be:
      - [] — the condition was malformed and was silently skipped, or it
             evaluated to False (did not fire).
      - [RiskZoneDict(...)] — the condition happened to be a syntactically
             valid expression that evaluated to True.

    The invariant is purely: no unhandled exception propagates out of
    evaluate() regardless of the condition string content.
    """
    _evaluator = RuleEvaluator()

    rule = RuleRecord(
        rule_id=_uuid_pbt.uuid4(),
        zone_id=_uuid_pbt.uuid4(),
        zone_name="bust",
        mathematical_condition=condition,
        severity_level="Reserve",
        explanation_message="Test propriété 8 — condition arbitraire.",
        version=1,
    )

    inp = RuleInput(
        rules=[rule],
        zone_measurements=zone_measurements,
        critical_zone_ids=[],
    )

    # The call must complete without raising any exception.
    try:
        result = _evaluator.evaluate(inp)
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(
            f"RuleEvaluator.evaluate() raised {type(exc).__name__} for "
            f"condition={condition!r}: {exc}"
        ) from exc

    # Result must be a list (never None)
    assert isinstance(result, list), (
        f"evaluate() must return a list, got {type(result).__name__!r}"
    )

    # Each item in the result — if any — must be a valid RiskZoneDict
    for rz in result:
        assert isinstance(rz, RiskZoneDict)
        assert rz.localized_verdict in ("Incompatible", "Reserve"), (
            f"localized_verdict must be 'Incompatible' or 'Reserve', "
            f"got {rz.localized_verdict!r}"
        )
