"""
AI Analyzer client for the Pattern Catalog (Module 4).

Provides a synchronous HTTP interface to an external Computer Vision service
that analyses a garment inspiration image and returns structured predictions.

Public API
----------
    analyze_image(image_bytes: bytes) -> AIAnalysisResult

    Reads ``AI_ANALYZER_URL`` from the environment:
    - If the variable is **absent or empty** → stub mode: returns deterministic
      fixture data immediately (useful for local development and automated tests).
    - If the variable is **set** → real mode: POSTs the image bytes to the
      configured URL with a 10-second timeout, parses the JSON response, and
      applies the confidence decision logic.

Custom exceptions
-----------------
    AILowConfidenceError  — raised when confidence < 0.70 (Req 1 AC2)
    AIUnavailableError    — raised when the AI service is unreachable, times
                            out, or returns an unexpected response shape
                            (Req 1 AC3)

Environment variables
---------------------
    AI_ANALYZER_URL  — full URL of the AI Analyzer endpoint, e.g.
                       ``https://cv.example.com/analyze``.
                       When absent or empty the stub implementation is used.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CONFIDENCE_THRESHOLD: float = 0.70
_REQUEST_TIMEOUT_SECONDS: int = 10

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class AILowConfidenceError(Exception):
    """Raised when the AI Analyzer returns a confidence score below 0.70.

    Attributes
    ----------
    confidence : float
        The confidence value returned by the AI service (0.0 – 1.0).
    """

    def __init__(self, confidence: float) -> None:
        self.confidence = confidence
        super().__init__(
            f"AI analysis confidence too low ({confidence:.2f} < "
            f"{_CONFIDENCE_THRESHOLD:.2f}): the submitted image is not "
            "recognisable. Please submit a clearer image of the garment."
        )


class AIUnavailableError(Exception):
    """Raised when the AI service is unreachable, times out, or returns an
    unexpected response shape.

    The ``__cause__`` attribute (set automatically by ``raise … from …``)
    holds the underlying exception when available.
    """


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class AIAnalysisResult:
    """Structured output from the AI Analyzer.

    Attributes
    ----------
    garment_type : str
        One of the ten garment-type enum values (e.g. ``"Dress"``).
    cut_type : str
        One of ``"Fitted"``, ``"Semi-fitted"``, or ``"Loose"``.
    critical_zones : list[str]
        Zone names returned by the AI (e.g. ``["Chest", "Waist", "Hips"]``).
        Unrecognised names are dropped by the service layer (case-insensitive
        match against the ``critical_zone`` seed table).
    confidence : float
        Confidence score in the range 0.0 – 1.0.
    """

    garment_type: str
    cut_type: str
    critical_zones: list[str] = field(default_factory=list)
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Stub implementation
# ---------------------------------------------------------------------------

_STUB_RESULT = AIAnalysisResult(
    garment_type="Dress",
    cut_type="Fitted",
    critical_zones=["Chest", "Waist", "Hips"],
    confidence=0.92,
)


def _stub_analyze(image_bytes: bytes) -> AIAnalysisResult:  # noqa: ARG001
    """Return deterministic fixture data for local development and tests.

    The result always passes the confidence threshold (0.92 ≥ 0.70) so that
    the full `POST /models/init` workflow can be exercised end-to-end without
    a real CV service.

    The *image_bytes* argument is accepted but intentionally ignored.
    """
    logger.debug(
        "AI Analyzer: stub mode active — returning fixture data "
        "(garment_type=%s, cut_type=%s, confidence=%.2f).",
        _STUB_RESULT.garment_type,
        _STUB_RESULT.cut_type,
        _STUB_RESULT.confidence,
    )
    return _STUB_RESULT


# ---------------------------------------------------------------------------
# Real HTTP implementation
# ---------------------------------------------------------------------------

def _real_analyze(image_bytes: bytes, url: str) -> AIAnalysisResult:
    """POST *image_bytes* to the AI Analyzer service and return the result.

    Args:
        image_bytes: Raw bytes of the inspiration image.
        url:         Full URL of the AI Analyzer endpoint.

    Returns:
        Parsed ``AIAnalysisResult``.

    Raises:
        AILowConfidenceError:  confidence < 0.70.
        AIUnavailableError:    network error, timeout, or unexpected response.
    """
    try:
        response = requests.post(
            url,
            files={"image": ("image.bin", image_bytes, "application/octet-stream")},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.exceptions.Timeout as exc:
        raise AIUnavailableError(
            f"AI Analyzer request timed out after {_REQUEST_TIMEOUT_SECONDS} s."
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        raise AIUnavailableError(
            "AI Analyzer is unreachable. Check AI_ANALYZER_URL and network connectivity."
        ) from exc
    except requests.exceptions.HTTPError as exc:
        raise AIUnavailableError(
            f"AI Analyzer returned an unexpected HTTP status: {exc.response.status_code}."
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise AIUnavailableError(
            f"AI Analyzer request failed: {exc}"
        ) from exc

    # --- Parse response body -------------------------------------------------
    try:
        payload: dict = response.json()
    except ValueError as exc:
        raise AIUnavailableError(
            "AI Analyzer returned a non-JSON response body."
        ) from exc

    try:
        garment_type: str = payload["garment_type"]
        cut_type: str = payload["cut_type"]
        critical_zones: list[str] = list(payload["critical_zones"])
        confidence: float = float(payload["confidence"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AIUnavailableError(
            f"AI Analyzer response has an unexpected shape: {exc}. "
            f"Received payload: {payload!r}"
        ) from exc

    # --- Confidence gate -------------------------------------------------------
    if confidence < _CONFIDENCE_THRESHOLD:
        raise AILowConfidenceError(confidence)

    return AIAnalysisResult(
        garment_type=garment_type,
        cut_type=cut_type,
        critical_zones=critical_zones,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def analyze_image(image_bytes: bytes) -> AIAnalysisResult:
    """Analyse *image_bytes* using the AI Analyzer service.

    Reads the ``AI_ANALYZER_URL`` environment variable at call time (not at
    module import) so that tests can patch it without reloading the module.

    - When ``AI_ANALYZER_URL`` is **absent or empty**, the stub implementation
      is used and fixture data is returned immediately.
    - When ``AI_ANALYZER_URL`` is **set**, the real HTTP call is made.

    Args:
        image_bytes: Raw bytes of the inspiration image to analyse.

    Returns:
        ``AIAnalysisResult`` with garment type, cut type, critical zones,
        and confidence score.

    Raises:
        AILowConfidenceError:  confidence < 0.70 (Req 1 AC2).
        AIUnavailableError:    service unreachable, timeout, or unexpected
                               response shape (Req 1 AC3).
    """
    ai_url: str = os.environ.get("AI_ANALYZER_URL", "").strip()

    if not ai_url:
        return _stub_analyze(image_bytes)

    return _real_analyze(image_bytes, ai_url)
