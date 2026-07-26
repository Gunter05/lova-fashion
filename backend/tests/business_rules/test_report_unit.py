"""
Unit tests for Module 7 — Final Result & Report (Synthesis).

Covers (Tasks 24–27):
  - build_display_hints()           — all three verdict values + incompatible zones
  - _validate_measurements()        — valid, negative, NULL inputs
  - CompatibilityEvaluatedEvent     — valid payloads, invalid verdict, CNI length
  - ReportSavedEvent                — field names and types for Module 1 contract
  - AdjustedMeasurementsSnapshot    — round-trip serialisation (Hypothesis)
  - build_display_hints() invariants — Hypothesis property tests (Tasks 34–36)

Req 2 AC3 · Req 3 AC1–5 · Req 9 AC2 · Design §Correctness Properties 1–5
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from app.modules.business_rules.report_schemas import (
    AdjustedMeasurementsSnapshot,
    CompatibilityEvaluatedEvent,
    DisplayHints,
    IncompatibleZoneItem,
    ReportSavedEvent,
)
from app.modules.business_rules.report_service import (
    ReportCreationError,
    _validate_measurements,
    build_display_hints,
)


# ──────────────────────────────────────────────────────────────────────────────
# Task 24: build_display_hints()
# ──────────────────────────────────────────────────────────────────────────────

class TestBuildDisplayHints:
    def test_compatible_is_green_no_zones(self):
        """Req 3 AC1 — compatible → green, highlight_zones=[]"""
        hints = build_display_hints("compatible", None)
        assert hints.verdict_color == "green"
        assert hints.highlight_zones == []

    def test_minor_adjustments_is_orange_no_zones(self):
        """Req 3 AC2 — minor_adjustments → orange, highlight_zones=[]"""
        hints = build_display_hints("minor_adjustments", None)
        assert hints.verdict_color == "orange"
        assert hints.highlight_zones == []

    def test_incompatible_is_red_with_zones(self):
        """Req 3 AC3 — incompatible → red, highlight_zones=[zone names]"""
        zones = [
            IncompatibleZoneItem(zone="bust",  reason="Too rigid"),
            IncompatibleZoneItem(zone="waist", reason="Not enough ease"),
        ]
        hints = build_display_hints("incompatible", zones)
        assert hints.verdict_color == "red"
        assert hints.highlight_zones == ["bust", "waist"]

    def test_incompatible_with_no_zones_still_red(self):
        """incompatible verdict with empty zones list → red, highlight_zones=[]"""
        hints = build_display_hints("incompatible", [])
        assert hints.verdict_color == "red"
        assert hints.highlight_zones == []

    def test_compatible_ignores_zones_arg(self):
        """compatible verdict ignores incompatible_zones even if provided."""
        zones = [IncompatibleZoneItem(zone="hips", reason="Test")]
        hints = build_display_hints("compatible", zones)
        assert hints.verdict_color == "green"
        assert hints.highlight_zones == []


# ──────────────────────────────────────────────────────────────────────────────
# Task 25: _validate_measurements()
# ──────────────────────────────────────────────────────────────────────────────

def _mock_adjustment(bust=90.0, waist=70.0, hips=95.0):
    adj = MagicMock()
    adj.id = uuid.uuid4()
    adj.adjusted_bust_cm  = bust
    adj.adjusted_waist_cm = waist
    adj.adjusted_hips_cm  = hips
    return adj


class TestValidateMeasurements:
    def test_all_valid_no_exception(self):
        """All zones >= 0 → no exception. Req 2 AC3"""
        _validate_measurements(_mock_adjustment(90.0, 70.0, 95.0))  # must not raise

    def test_zero_is_valid(self):
        """0.0 is exactly on the boundary — must not raise (clamped by Module 5)."""
        _validate_measurements(_mock_adjustment(0.0, 70.0, 95.0))

    def test_negative_bust_raises(self):
        """Negative bust circumference → ReportCreationError with zone name."""
        with pytest.raises(ReportCreationError) as exc_info:
            _validate_measurements(_mock_adjustment(bust=-1.0))
        assert "adjusted_bust_cm" in exc_info.value.message

    def test_negative_waist_raises(self):
        """Negative waist circumference → ReportCreationError."""
        with pytest.raises(ReportCreationError) as exc_info:
            _validate_measurements(_mock_adjustment(waist=-0.1))
        assert "adjusted_waist_cm" in exc_info.value.message

    def test_negative_hips_raises(self):
        """Negative hips circumference → ReportCreationError."""
        with pytest.raises(ReportCreationError) as exc_info:
            _validate_measurements(_mock_adjustment(hips=-5.0))
        assert "adjusted_hips_cm" in exc_info.value.message

    def test_null_value_raises(self):
        """NULL (None) measurement → ReportCreationError. Req 2 AC3"""
        with pytest.raises(ReportCreationError):
            _validate_measurements(_mock_adjustment(bust=None))


# ──────────────────────────────────────────────────────────────────────────────
# Task 26: CompatibilityEvaluatedEvent schema
# ──────────────────────────────────────────────────────────────────────────────

def _valid_compatible_payload(**overrides) -> dict:
    base = {
        "type": "compatibility.evaluated",
        "emitted_at": "2025-07-25T10:00:00Z",
        "cni": "ABC123456",
        "adjustment_id": str(uuid.uuid4()),
        "fabric_id": str(uuid.uuid4()),
        "model_id": str(uuid.uuid4()),
        "verdict": "compatible",
        "advice": "Great choice!",
    }
    base.update(overrides)
    return base


class TestCompatibilityEvaluatedEvent:
    def test_valid_compatible_payload_parses(self):
        """Valid compatible event with no zones parses correctly. Req 1 AC1"""
        event = CompatibilityEvaluatedEvent.model_validate(_valid_compatible_payload())
        assert event.verdict == "compatible"
        assert event.incompatible_zones is None

    def test_valid_incompatible_with_zones_parses(self):
        """Valid incompatible event with zones populates the field. Req 3 AC4"""
        payload = _valid_compatible_payload(
            verdict="incompatible",
            incompatible_zones=[{"zone": "bust", "reason": "Too rigid"}],
        )
        event = CompatibilityEvaluatedEvent.model_validate(payload)
        assert event.verdict == "incompatible"
        assert len(event.incompatible_zones) == 1
        assert event.incompatible_zones[0].zone == "bust"

    def test_invalid_verdict_raises_validation_error(self):
        """Verdict not in allowed set → ValidationError. Req 3 AC5"""
        with pytest.raises(ValidationError):
            CompatibilityEvaluatedEvent.model_validate(
                _valid_compatible_payload(verdict="unknown_verdict")
            )

    def test_cni_too_short_raises_validation_error(self):
        """CNI shorter than 9 chars → ValidationError."""
        with pytest.raises(ValidationError):
            CompatibilityEvaluatedEvent.model_validate(
                _valid_compatible_payload(cni="SHORT")
            )

    def test_cni_too_long_raises_validation_error(self):
        """CNI longer than 9 chars → ValidationError."""
        with pytest.raises(ValidationError):
            CompatibilityEvaluatedEvent.model_validate(
                _valid_compatible_payload(cni="TOOLONGCNI0")
            )

    def test_minor_adjustments_verdict_parses(self):
        """minor_adjustments is a valid verdict."""
        event = CompatibilityEvaluatedEvent.model_validate(
            _valid_compatible_payload(verdict="minor_adjustments")
        )
        assert event.verdict == "minor_adjustments"


# ──────────────────────────────────────────────────────────────────────────────
# Task 27: ReportSavedEvent — Module 1 contract check
# ──────────────────────────────────────────────────────────────────────────────

class TestReportSavedEvent:
    def test_field_names_and_types(self):
        """
        Verify field names and types exactly match Module 1's handle_report_saved
        contract: type (str), cni (str), report_id (str), date_generation (str).
        Req 9 AC2
        """
        event = ReportSavedEvent(
            cni="ABC123456",
            report_id=str(uuid.uuid4()),
            date_generation=datetime.now(timezone.utc).isoformat(),
        )
        dumped = event.model_dump()
        assert dumped["type"] == "report.saved"
        assert isinstance(dumped["cni"], str)
        assert isinstance(dumped["report_id"], str)
        assert isinstance(dumped["date_generation"], str)

    def test_default_type_is_report_saved(self):
        """type field defaults to 'report.saved' without explicit assignment."""
        event = ReportSavedEvent(
            cni="ABC123456",
            report_id="some-uuid",
            date_generation="2025-07-25T10:00:00+00:00",
        )
        assert event.type == "report.saved"


# ──────────────────────────────────────────────────────────────────────────────
# Task 34: Hypothesis — build_display_hints() invariants
# ──────────────────────────────────────────────────────────────────────────────

VALID_VERDICTS = ["compatible", "incompatible", "minor_adjustments"]

zone_strategy = st.lists(
    st.builds(
        IncompatibleZoneItem,
        zone=st.text(min_size=1, max_size=20),
        reason=st.text(min_size=1, max_size=100),
    ),
    min_size=0,
    max_size=10,
)


@given(
    verdict=st.sampled_from(VALID_VERDICTS),
    zones=zone_strategy,
)
@settings(max_examples=100)
def test_hint_color_always_in_valid_set(verdict: str, zones: list):
    """
    Property 1: For all valid verdicts, verdict_color is always one of
    {"green", "orange", "red"} and highlight_zones is always a list.
    Design §Correctness Property 1 · Req 3 AC1–3
    """
    hints = build_display_hints(verdict, zones if zones else None)
    assert hints.verdict_color in ("green", "orange", "red")
    assert isinstance(hints.highlight_zones, list)


@given(
    verdict=st.sampled_from(["compatible", "minor_adjustments"]),
    zones=zone_strategy,
)
@settings(max_examples=100)
def test_non_incompatible_has_empty_zones(verdict: str, zones: list):
    """
    Property 2: highlight_zones is always [] for non-incompatible verdicts.
    Design §Correctness Property 2 · Req 3 AC1–2
    """
    hints = build_display_hints(verdict, zones)
    assert hints.highlight_zones == []


@given(zones=zone_strategy)
@settings(max_examples=100)
def test_incompatible_zone_length_matches(zones: list):
    """
    Property 3: len(highlight_zones) == len(incompatible_zones) when incompatible.
    Design §Correctness Property 3 · Req 3 AC3
    """
    hints = build_display_hints("incompatible", zones)
    assert len(hints.highlight_zones) == len(zones)


# ──────────────────────────────────────────────────────────────────────────────
# Task 35: Hypothesis — AdjustedMeasurementsSnapshot round-trip
# ──────────────────────────────────────────────────────────────────────────────

_float_strategy = st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False)
_ease_strategy  = st.floats(min_value=-5.0, max_value=10.0, allow_nan=False, allow_infinity=False)
_source_strategy = st.sampled_from(["rule", "default_fallback"])


@given(
    adj_bust=_float_strategy,
    adj_waist=_float_strategy,
    adj_hips=_float_strategy,
    bust_ease=_ease_strategy,
    waist_ease=_ease_strategy,
    hips_ease=_ease_strategy,
    ease_source=_source_strategy,
)
@settings(max_examples=100)
def test_snapshot_round_trip(
    adj_bust, adj_waist, adj_hips, bust_ease, waist_ease, hips_ease, ease_source
):
    """
    Property 4: AdjustedMeasurementsSnapshot round-trips through model_dump()
    without data loss. Design §Correctness Property 4 · Req 2 AC1
    """
    snap = AdjustedMeasurementsSnapshot(
        adjusted_bust_cm=adj_bust,
        adjusted_waist_cm=adj_waist,
        adjusted_hips_cm=adj_hips,
        bust_ease_cm=bust_ease,
        waist_ease_cm=waist_ease,
        hips_ease_cm=hips_ease,
        ease_source=ease_source,
    )
    dumped = snap.model_dump()
    restored = AdjustedMeasurementsSnapshot.model_validate(dumped)
    assert restored.adjusted_bust_cm  == snap.adjusted_bust_cm
    assert restored.adjusted_waist_cm == snap.adjusted_waist_cm
    assert restored.adjusted_hips_cm  == snap.adjusted_hips_cm
    assert restored.bust_ease_cm      == snap.bust_ease_cm
    assert restored.waist_ease_cm     == snap.waist_ease_cm
    assert restored.hips_ease_cm      == snap.hips_ease_cm
    assert restored.ease_source       == snap.ease_source


# ──────────────────────────────────────────────────────────────────────────────
# Task 36: Hypothesis — _validate_measurements() error condition
# ──────────────────────────────────────────────────────────────────────────────

@given(
    bust=st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
    waist=st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
    hips=st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_validate_no_error_for_valid_values(bust, waist, hips):
    """
    Property 5a: For any three values all >= 0 no exception is raised.
    Design §Correctness Property 5 · Req 2 AC3
    """
    _validate_measurements(_mock_adjustment(bust, waist, hips))  # must not raise


@given(
    bust=st.floats(max_value=-0.001, allow_nan=False, allow_infinity=False),
    waist=st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
    hips=st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_validate_error_for_negative_value(bust, waist, hips):
    """
    Property 5b: For any set where at least one value is < 0 ReportCreationError
    is always raised. Design §Correctness Property 5 · Req 2 AC3
    """
    with pytest.raises(ReportCreationError):
        _validate_measurements(_mock_adjustment(bust, waist, hips))
