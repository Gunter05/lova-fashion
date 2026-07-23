"""
Body shape classifier for Module 2 — Photo Capture & Measurement Estimation.
Task T-05.1 — AC-08.1, AC-08.2, Design §7

Five silhouette codes, evaluated in strict priority order:
    1. HOURGLASS        (Sablier X)
    2. PEAR             (Poire A)
    3. INVERTED_TRIANGLE (Triangle inversé V)
    4. APPLE            (Pomme O)
    5. RECTANGLE        (Rectangle H)  ← fallback

Rules agreed in requirements.md AC-08.1:
    HOURGLASS        : waist/bust ≤ 0.75 AND waist/hips ≤ 0.75 AND |bust − hips| ≤ 5 cm
    PEAR             : hips > bust + 5 cm AND waist < hips
    INVERTED_TRIANGLE: bust > hips + 5 cm
    APPLE            : waist ≥ bust OR waist ≥ hips
    RECTANGLE        : none of the above
"""

from __future__ import annotations

from typing import Literal

SilhouetteCode = Literal[
    "HOURGLASS",
    "PEAR",
    "INVERTED_TRIANGLE",
    "APPLE",
    "RECTANGLE",
]


class BodyShapeClassifier:
    """
    Stateless classifier — instantiate once and reuse.

    Usage
    -----
        classifier = BodyShapeClassifier()
        code = classifier.classify(bust=90.0, waist=68.0, hips=93.0)
        # → "HOURGLASS"
    """

    def classify(
        self,
        bust: float,
        waist: float,
        hips: float,
    ) -> SilhouetteCode:
        """
        Return the silhouette code for the given measurements.

        Parameters
        ----------
        bust  : Estimated bust circumference in cm.
        waist : Estimated waist circumference in cm.
        hips  : Estimated hip circumference in cm.

        Returns
        -------
        SilhouetteCode : One of HOURGLASS, PEAR, INVERTED_TRIANGLE, APPLE, RECTANGLE.

        Raises
        ------
        ValueError : If any measurement is non-positive (guards against bad CV output).
        """
        if bust <= 0 or waist <= 0 or hips <= 0:
            raise ValueError(
                f"Les mesures doivent être positives "
                f"(buste={bust}, taille={waist}, hanches={hips})."
            )

        # ------------------------------------------------------------------
        # Priority 1 — Hourglass (Sablier X)
        # AC-08.1 row 1
        # ------------------------------------------------------------------
        if (
            waist / bust <= 0.75
            and waist / hips <= 0.75
            and abs(bust - hips) <= 5.0
        ):
            return "HOURGLASS"

        # ------------------------------------------------------------------
        # Priority 2 — Pear (Poire A)
        # AC-08.1 row 2
        # ------------------------------------------------------------------
        if hips > bust + 5.0 and waist < hips:
            return "PEAR"

        # ------------------------------------------------------------------
        # Priority 3 — Inverted Triangle (Triangle inversé V)
        # AC-08.1 row 3
        # ------------------------------------------------------------------
        if bust > hips + 5.0:
            return "INVERTED_TRIANGLE"

        # ------------------------------------------------------------------
        # Priority 4 — Apple (Pomme O)
        # AC-08.1 row 4
        # ------------------------------------------------------------------
        if waist >= bust or waist >= hips:
            return "APPLE"

        # ------------------------------------------------------------------
        # Priority 5 — Rectangle (Rectangle H)  — fallback
        # AC-08.1 row 5
        # ------------------------------------------------------------------
        return "RECTANGLE"
