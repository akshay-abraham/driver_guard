"""
vision/metrics.py
==================
Pure geometry functions that turn raw MediaPipe Face Mesh landmarks into the
two scalar measurements the whole decision engine is built on:

    * EAR (Eye Aspect Ratio)   - how open the eyes are
    * MAR (Mouth Aspect Ratio) - how open the mouth is

These are intentionally simple, well-established formulas (Soukupova & Cech,
2016 for EAR) so the whole pipeline stays explainable end-to-end: a judge can
look at a single frame, measure the same distances with a ruler, and get the
same number the system computed.

No OpenCV / MediaPipe objects are imported here — this module only works with
plain (x, y) coordinate tuples, which makes it trivially unit-testable.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple, Sequence

from backend.config import LEFT_EYE, RIGHT_EYE, MOUTH

Point = Tuple[float, float]


def _dist(p1: Point, p2: Point) -> float:
    """Euclidean distance between two 2D points."""
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def _eye_aspect_ratio(points: Dict[str, Tuple[Point, Point]]) -> float:
    """
    Classic EAR formula generalised to two vertical pairs for extra stability:

        EAR = (||p_v1a - p_v1b|| + ||p_v2a - p_v2b||) / (2 * ||p_h_a - p_h_b||)

    A wide-open eye has a large vertical distance relative to its horizontal
    width -> higher EAR. A closed eye collapses vertically -> EAR approaches 0.
    """
    h_a, h_b = points["horizontal"]
    v1_a, v1_b = points["vertical_1"]
    v2_a, v2_b = points["vertical_2"]

    horizontal = _dist(h_a, h_b)
    if horizontal < 1e-6:
        return 0.0

    vertical = _dist(v1_a, v1_b) + _dist(v2_a, v2_b)
    return vertical / (2.0 * horizontal)


def _mouth_aspect_ratio(points: Dict[str, Tuple[Point, Point]]) -> float:
    """
    Same idea as EAR but for the mouth, averaged across three vertical pairs
    (inner lip + two side pairs) for robustness against asymmetric mouth
    shapes while talking.
    """
    h_a, h_b = points["horizontal"]
    v1_a, v1_b = points["vertical_1"]
    v2_a, v2_b = points["vertical_2"]
    v3_a, v3_b = points["vertical_3"]

    horizontal = _dist(h_a, h_b)
    if horizontal < 1e-6:
        return 0.0

    vertical = _dist(v1_a, v1_b) + _dist(v2_a, v2_b) + _dist(v3_a, v3_b)
    return vertical / (3.0 * horizontal)


def _resolve(landmark_map: Dict[str, Tuple[int, int]], landmarks: Sequence[Point]) -> Dict[str, Tuple[Point, Point]]:
    resolved: Dict[str, Tuple[Point, Point]] = {}
    for key, (i1, i2) in landmark_map.items():
        resolved[key] = (landmarks[i1], landmarks[i2])
    return resolved


def compute_ear(landmarks: Sequence[Point]) -> Tuple[float, float, float]:
    """
    Returns (left_ear, right_ear, average_ear) for a full 468/478-point
    MediaPipe landmark list expressed as pixel (or normalised) coordinates.
    """
    left = _eye_aspect_ratio(_resolve(LEFT_EYE, landmarks))
    right = _eye_aspect_ratio(_resolve(RIGHT_EYE, landmarks))
    return left, right, (left + right) / 2.0


def compute_mar(landmarks: Sequence[Point]) -> float:
    """Returns the Mouth Aspect Ratio for a full MediaPipe landmark list."""
    return _mouth_aspect_ratio(_resolve(MOUTH, landmarks))
