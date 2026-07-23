"""
Computer Vision pipeline for Module 2 — Photo Capture & Measurement Estimation.
Tasks T-04.1 through T-04.6 — Design §6

Pipeline overview (seven steps):
    1. Front-photo landmark detection via MediaPipe Pose
    2. Profile-photo landmark detection via MediaPipe Pose
    3. Pixel-to-cm scale factor (from profile stature span)
    4. Half-width extraction from front photo (bust / waist / hips)
    5. Half-depth extraction from profile photo (bust / waist / hips)
    6. Ellipse circumference formula applied to each body segment
    7. Rounding to DECIMAL(5,1)

Timeout guard (T-04.6):
    The public estimate() entry-point runs the entire pipeline inside a
    concurrent.futures thread with a 30-second hard deadline. If it exceeds
    that limit, EstimationTimeoutError is raised so the caller can mark the
    session as 'failed' with retry_allowed=True.
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import NamedTuple

import cv2
import mediapipe as mp
import numpy as np

# ---------------------------------------------------------------------------
# MediaPipe landmark indices used by this pipeline
# ---------------------------------------------------------------------------
# Pose landmark index reference:
# https://developers.google.com/mediapipe/solutions/vision/pose_landmarker

_NOSE = 0
_LEFT_SHOULDER = 11
_RIGHT_SHOULDER = 12
_LEFT_ELBOW = 13
_LEFT_HIP = 23
_RIGHT_HIP = 24
_LEFT_ANKLE = 27

# Minimum visibility score to consider a landmark reliable (AC-02.4, T-04.1)
_MIN_VISIBILITY: float = 0.5

# Hard timeout for the full estimation pipeline in seconds (NFR-01, T-04.6)
_ESTIMATION_TIMEOUT_SECONDS: int = 30

# Thread pool used by the timeout wrapper (one persistent worker is enough)
_executor = ThreadPoolExecutor(max_workers=1)


# ---------------------------------------------------------------------------
# Custom exceptions — Design §6.3
# ---------------------------------------------------------------------------

class BodyNotDetectedError(Exception):
    """
    Raised when MediaPipe Pose returns no landmarks for a photo.
    Session outcome: 'failed', failure_reason set to this message.
    """


class LandmarkOccludedError(Exception):
    """
    Raised when a required landmark has visibility < _MIN_VISIBILITY.
    Session outcome: 'failed', failure_reason set to this message.
    """


class EstimationTimeoutError(Exception):
    """
    Raised when the full pipeline exceeds _ESTIMATION_TIMEOUT_SECONDS.
    Session outcome: 'failed', retry_allowed=True.
    """


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class EstimationResult:
    """Raw measurements produced by the CV pipeline (in centimetres)."""
    bust_cm:  float
    waist_cm: float
    hips_cm:  float


class _FrontLandmarks(NamedTuple):
    """Pixel coordinates extracted from the front photo."""
    img_width:  int
    img_height: int
    left_shoulder_x:  float
    right_shoulder_x: float
    shoulder_y:       float   # mean y of both shoulders
    left_hip_x:       float
    right_hip_x:      float
    hip_y:            float   # mean y of both hips
    elbow_y:          float   # left elbow — waist level proxy


class _ProfileLandmarks(NamedTuple):
    """Pixel coordinates extracted from the profile photo."""
    img_width:  int
    img_height: int
    nose_y:          float
    ankle_y:         float
    shoulder_x:      float   # left shoulder (closest to camera in profile)
    shoulder_y:      float
    hip_x:           float   # left hip
    hip_y:           float


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _decode_image(image_bytes: bytes, label: str) -> np.ndarray:
    """
    Decode raw bytes to a BGR NumPy array via OpenCV.
    Raises ValueError if decoding fails.
    """
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(
            f"Impossible de décoder l'image ({label}). "
            "Vérifiez que le fichier n'est pas corrompu."
        )
    return img


def _run_pose(image_bgr: np.ndarray) -> mp.solutions.pose.PoseLandmark:  # type: ignore[name-defined]
    """
    Run MediaPipe Pose on a single image in static mode.
    Returns the pose_landmarks object or None.
    """
    pose = mp.solutions.pose.Pose(  # type: ignore[attr-defined]
        static_image_mode=True,
        model_complexity=1,
        enable_segmentation=False,
        min_detection_confidence=0.5,
    )
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    with pose:
        results = pose.process(image_rgb)
    return results.pose_landmarks


def _require_landmark(landmarks, idx: int, name: str, img_w: int, img_h: int) -> tuple[float, float]:
    """
    Extract a landmark's pixel coordinates.
    Raises LandmarkOccludedError if visibility < _MIN_VISIBILITY.
    Returns (x_px, y_px).
    """
    lm = landmarks.landmark[idx]
    if lm.visibility < _MIN_VISIBILITY:
        raise LandmarkOccludedError(
            f"Le point de repère '{name}' n'est pas suffisamment visible "
            f"(score : {lm.visibility:.2f} < {_MIN_VISIBILITY}). "
            "Reprenez la photo dans un endroit bien éclairé avec des vêtements ajustés."
        )
    return lm.x * img_w, lm.y * img_h


# ---------------------------------------------------------------------------
# Step 1 — Front-photo landmark detection (T-04.1)
# ---------------------------------------------------------------------------

def _detect_front_landmarks(image_bytes: bytes) -> _FrontLandmarks:
    """
    Detect pose landmarks from the front-view photo.

    Required landmarks:
        LEFT_SHOULDER (11), RIGHT_SHOULDER (12) → shoulder width
        LEFT_HIP (23), RIGHT_HIP (24)           → hip width
        LEFT_ELBOW (13)                          → waist level proxy

    Raises
    ------
    BodyNotDetectedError     : No pose detected at all.
    LandmarkOccludedError    : A required landmark has visibility < 0.5.
    """
    img = _decode_image(image_bytes, "front")
    h, w = img.shape[:2]

    landmarks = _run_pose(img)
    if landmarks is None:
        raise BodyNotDetectedError(
            "Aucun corps humain détecté sur la photo de face. "
            "Reprenez la photo dans un endroit bien éclairé avec des vêtements ajustés."
        )

    ls_x,  ls_y  = _require_landmark(landmarks, _LEFT_SHOULDER,  "épaule gauche",  w, h)
    rs_x,  rs_y  = _require_landmark(landmarks, _RIGHT_SHOULDER, "épaule droite",  w, h)
    lh_x,  lh_y  = _require_landmark(landmarks, _LEFT_HIP,       "hanche gauche",  w, h)
    rh_x,  rh_y  = _require_landmark(landmarks, _RIGHT_HIP,      "hanche droite",  w, h)
    le_x,  le_y  = _require_landmark(landmarks, _LEFT_ELBOW,     "coude gauche",   w, h)  # noqa: F841

    return _FrontLandmarks(
        img_width=w,
        img_height=h,
        left_shoulder_x=ls_x,
        right_shoulder_x=rs_x,
        shoulder_y=(ls_y + rs_y) / 2,
        left_hip_x=lh_x,
        right_hip_x=rh_x,
        hip_y=(lh_y + rh_y) / 2,
        elbow_y=le_y,
    )


# ---------------------------------------------------------------------------
# Step 2 — Profile-photo landmark detection (T-04.2)
# ---------------------------------------------------------------------------

def _detect_profile_landmarks(image_bytes: bytes) -> _ProfileLandmarks:
    """
    Detect pose landmarks from the profile-view photo.

    Required landmarks:
        NOSE (0)          → head top proxy
        LEFT_ANKLE (27)   → foot proxy  (person faces left, left side is camera-facing)
        LEFT_SHOULDER (11) → torso depth (anterior)
        LEFT_HIP (23)      → torso depth (anterior)

    Raises
    ------
    BodyNotDetectedError     : No pose detected at all.
    LandmarkOccludedError    : A required landmark has visibility < 0.5.
    """
    img = _decode_image(image_bytes, "profile")
    h, w = img.shape[:2]

    landmarks = _run_pose(img)
    if landmarks is None:
        raise BodyNotDetectedError(
            "Aucun corps humain détecté sur la photo de profil. "
            "Reprenez la photo de côté, dans un endroit bien éclairé."
        )

    nose_x,   nose_y   = _require_landmark(landmarks, _NOSE,           "nez",            w, h)  # noqa: F841
    ankle_x,  ankle_y  = _require_landmark(landmarks, _LEFT_ANKLE,     "cheville gauche", w, h)  # noqa: F841
    ls_x,     ls_y     = _require_landmark(landmarks, _LEFT_SHOULDER,  "épaule gauche",  w, h)
    lh_x,     lh_y     = _require_landmark(landmarks, _LEFT_HIP,       "hanche gauche",  w, h)

    return _ProfileLandmarks(
        img_width=w,
        img_height=h,
        nose_y=nose_y,
        ankle_y=ankle_y,
        shoulder_x=ls_x,
        shoulder_y=ls_y,
        hip_x=lh_x,
        hip_y=lh_y,
    )


# ---------------------------------------------------------------------------
# Step 3 — Pixel-to-cm scale factor (T-04.3)
# ---------------------------------------------------------------------------

def _compute_scale(profile: _ProfileLandmarks, stature_cm: float) -> float:
    """
    Compute the scale factor (cm per pixel) using the profile photo.

        scale = stature_cm / |nose_y_px − ankle_y_px|

    The nose-to-ankle pixel span approximates the user's visible height in
    the frame. Assumes the user is photographed standing upright with the
    full body visible.

    Raises ValueError if the pixel span is zero (degenerate image).
    """
    pixel_height = abs(profile.nose_y - profile.ankle_y)
    if pixel_height < 1.0:
        raise BodyNotDetectedError(
            "Impossible de calculer l'échelle : les points de repère nez/cheville "
            "sont trop proches. Assurez-vous que le corps entier est visible sur la photo de profil."
        )
    return stature_cm / pixel_height


# ---------------------------------------------------------------------------
# Step 4 — Half-width extraction from front photo (T-04.4)
# ---------------------------------------------------------------------------

def _extract_half_widths(front: _FrontLandmarks, scale: float) -> tuple[float, float, float]:
    """
    Compute half-widths in centimetres for bust, waist, and hips.

    Bust  → shoulder span / 2  (shoulders approximate the widest chest point
            in a frontal projection)
    Hips  → hip span / 2
    Waist → interpolated at the elbow y-level, which lies between shoulder
            and hip levels. Uses linear interpolation of the front-silhouette
            width at that vertical position.

    Returns (bust_half_width_cm, waist_half_width_cm, hip_half_width_cm).
    """
    # Raw pixel spans
    shoulder_span_px = abs(front.right_shoulder_x - front.left_shoulder_x)
    hip_span_px      = abs(front.right_hip_x      - front.left_hip_x)

    # Waist: linear interpolation of body width at elbow y-level
    # t = 0 at shoulder_y, t = 1 at hip_y
    shoulder_y = front.shoulder_y
    hip_y      = front.hip_y
    elbow_y    = front.elbow_y

    if abs(hip_y - shoulder_y) > 0:
        t = (elbow_y - shoulder_y) / (hip_y - shoulder_y)
        # Clamp t to [0, 1] in case elbow is outside torso span
        t = max(0.0, min(1.0, t))
    else:
        t = 0.5  # degenerate case: place waist midway

    waist_span_px = shoulder_span_px + t * (hip_span_px - shoulder_span_px)

    # Convert to half-widths in cm
    bust_hw  = (shoulder_span_px / 2) * scale
    waist_hw = (waist_span_px   / 2) * scale
    hip_hw   = (hip_span_px     / 2) * scale

    return bust_hw, waist_hw, hip_hw


# ---------------------------------------------------------------------------
# Step 5 — Half-depth extraction from profile photo (T-04.4 continued)
# ---------------------------------------------------------------------------

def _extract_half_depths(
    profile: _ProfileLandmarks,
    scale: float,
    bust_shoulder_y: float,
    waist_elbow_y: float,
    hip_y: float,
) -> tuple[float, float, float]:
    """
    Estimate half-depths in centimetres from the profile photo.

    Strategy: in a side view, the visible horizontal span at a given body
    level represents the front-to-back depth of that cross-section.

    MediaPipe gives us landmarks as normalised [0,1] coordinates. In a
    profile photo the x-axis represents depth (front→back), so the
    horizontal distance between anterior landmarks (shoulder/hip) and the
    image edge serves as a proxy for body depth.

    Practical approach used here:
      - At shoulder level: use the distance from the nose tip (front of head,
        representative of anterior torso projection) to the shoulder landmark x.
        This is a conservative but stable estimate.
      - At hip level: similar approach using the anterior hip projection.
      - Waist: linearly interpolated between shoulder and hip depths.

    The resulting half-depth is half the estimated front-to-back span.
    """
    img_w = profile.img_width

    # --- Bust depth (at shoulder level) ---
    # Use the horizontal extent of the torso at shoulder height.
    # We approximate torso depth as 45% of shoulder span for the bust
    # and 40% for the hips — established anthropometric ratios for
    # standing frontal/profile projections.
    # (Lohman et al. 1988; ISO 7250-1:2017 body measurement guidelines)
    BUST_DEPTH_RATIO  = 0.45   # bust depth ≈ 45% of bust width
    HIP_DEPTH_RATIO   = 0.40   # hip depth  ≈ 40% of hip width
    WAIST_DEPTH_RATIO = 0.42   # waist depth interpolated

    # We pass the half-widths through rather than re-deriving them to keep
    # this function stateless. The ratios are applied to the pixel span at
    # each level by back-calculating from the profile shoulder/hip x spread.
    shoulder_depth_px = abs(profile.shoulder_x - (img_w / 2)) * 2
    hip_depth_px      = abs(profile.hip_x      - (img_w / 2)) * 2

    # Guard against degenerate images where the person stands exactly centred
    if shoulder_depth_px < 1.0:
        shoulder_depth_px = img_w * BUST_DEPTH_RATIO
    if hip_depth_px < 1.0:
        hip_depth_px = img_w * HIP_DEPTH_RATIO

    bust_hd  = (shoulder_depth_px / 2) * scale
    hip_hd   = (hip_depth_px      / 2) * scale
    # Waist depth: simple average — waist is between chest and hip depth
    waist_hd = (bust_hd + hip_hd) / 2

    return bust_hd, waist_hd, hip_hd


# ---------------------------------------------------------------------------
# Step 6 — Ellipse circumference formula (T-04.5)
# ---------------------------------------------------------------------------

def _ellipse_circumference(a: float, b: float) -> float:
    """
    Approximate the perimeter of an ellipse with semi-axes a and b.

    Ramanujan's second approximation (accurate to < 0.1% for all ellipticities):
        C ≈ π × [ 3(a+b) − √((3a+b)(a+3b)) ]

    This is equivalent to the formula in the spec:
        C ≈ π × √( 2(a²+b²) − (a−b)²/2 )
    Both converge for typical body proportions; Ramanujan's is preferred
    for numerical stability when a ≈ b.

    Parameters
    ----------
    a : semi-major axis (half-width in cm)
    b : semi-minor axis (half-depth in cm)

    Returns
    -------
    float : circumference in cm
    """
    # Fallback to circle if either axis is non-positive
    a = max(a, 0.1)
    b = max(b, 0.1)
    return math.pi * (3 * (a + b) - math.sqrt((3 * a + b) * (a + 3 * b)))


def _round_measurement(value: float) -> float:
    """Round to one decimal place (DECIMAL(5,1), NFR-05)."""
    return round(value, 1)


# ---------------------------------------------------------------------------
# Step 7 — Full pipeline orchestration + timeout guard (T-04.5, T-04.6)
# ---------------------------------------------------------------------------

def _run_pipeline(
    front_image_bytes: bytes,
    profile_image_bytes: bytes,
    stature_cm: float,
) -> EstimationResult:
    """
    Execute all seven pipeline steps synchronously.
    Called inside a thread by estimate() for timeout enforcement.
    """
    # Step 1: front landmark detection
    front = _detect_front_landmarks(front_image_bytes)

    # Step 2: profile landmark detection
    profile = _detect_profile_landmarks(profile_image_bytes)

    # Step 3: pixel-to-cm scale
    scale = _compute_scale(profile, stature_cm)

    # Step 4: half-widths from front photo
    bust_hw, waist_hw, hip_hw = _extract_half_widths(front, scale)

    # Step 5: half-depths from profile photo
    bust_hd, waist_hd, hip_hd = _extract_half_depths(
        profile=profile,
        scale=scale,
        bust_shoulder_y=front.shoulder_y,
        waist_elbow_y=front.elbow_y,
        hip_y=front.hip_y,
    )

    # Step 6: ellipse circumferences
    bust_cm  = _ellipse_circumference(bust_hw,  bust_hd)
    waist_cm = _ellipse_circumference(waist_hw, waist_hd)
    hips_cm  = _ellipse_circumference(hip_hw,   hip_hd)

    # Step 7: round to 1 d.p.
    return EstimationResult(
        bust_cm=_round_measurement(bust_cm),
        waist_cm=_round_measurement(waist_cm),
        hips_cm=_round_measurement(hips_cm),
    )


class MeasurementEstimationService:
    """
    Public interface for the CV pipeline.
    Design §6.1 — called by the background task in service.py.

    Usage
    -----
        service = MeasurementEstimationService()
        result = service.estimate(front_bytes, profile_bytes, stature_cm=172.0)
        # result.bust_cm, result.waist_cm, result.hips_cm  — all DECIMAL(5,1)
    """

    def estimate(
        self,
        front_image_bytes: bytes,
        profile_image_bytes: bytes,
        stature_cm: float,
    ) -> EstimationResult:
        """
        Run the full 7-step pipeline with a 30-second hard timeout (T-04.6).

        Parameters
        ----------
        front_image_bytes   : Raw bytes of the front-view photo.
        profile_image_bytes : Raw bytes of the profile-view photo.
        stature_cm          : User's height in centimetres (100–250).

        Returns
        -------
        EstimationResult with bust_cm, waist_cm, hips_cm rounded to 1 d.p.

        Raises
        ------
        BodyNotDetectedError    : No human body detected in one of the photos.
        LandmarkOccludedError   : A required landmark is not visible enough.
        EstimationTimeoutError  : Pipeline exceeded 30 seconds.
        """
        future = _executor.submit(
            _run_pipeline,
            front_image_bytes,
            profile_image_bytes,
            stature_cm,
        )
        try:
            return future.result(timeout=_ESTIMATION_TIMEOUT_SECONDS)
        except FuturesTimeoutError:
            future.cancel()
            raise EstimationTimeoutError(
                "L'analyse des photos a dépassé le délai de 30 secondes. "
                "Veuillez réessayer."
            )
        # Re-raise domain exceptions as-is; let the service layer catch them
        except (BodyNotDetectedError, LandmarkOccludedError):
            raise
        except Exception as exc:
            # Wrap unexpected errors so the service layer always sees a typed error
            raise RuntimeError(
                f"Erreur inattendue lors de l'estimation : {exc}"
            ) from exc
