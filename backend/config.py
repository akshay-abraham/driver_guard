"""
config.py
=========
Single source of truth for every tunable value in the Driver Monitoring System.

Why this file exists
---------------------
Hackathon judges (and future maintainers) should be able to open ONE file and
understand — and change — every threshold that drives the decision engine.
No magic numbers live anywhere else in the codebase. This mirrors the way
firmware projects (e.g. Arduino sketches) put all `#define` constants at the
top of the file.

Everything here is also exposed live to the frontend "Settings" panel via
GET /api/config and can be changed at runtime via the WebSocket control
channel (POST /api/config or the `config_update` WS message) — the running
DecisionEngine reads from this same object, so changes take effect on the
very next frame.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict


# --------------------------------------------------------------------------- #
# CAMERA / SERVER
# --------------------------------------------------------------------------- #

CAMERA_INDEX: int = 0                 # OS default webcam. Change if you have multiple cameras.
CAMERA_WIDTH: int = 640
CAMERA_HEIGHT: int = 480
CAMERA_FPS_TARGET: int = 30           # Requested capture FPS (actual FPS is measured, not assumed)

SERVER_HOST: str = "0.0.0.0"
SERVER_PORT: int = 8000

JPEG_QUALITY: int = 75                # Frame compression quality sent over the WebSocket (1-100)
STREAM_MAX_WIDTH: int = 480           # Frame is downscaled before encoding, to save bandwidth/CPU


# --------------------------------------------------------------------------- #
# MEDIAPIPE FACE MESH
# --------------------------------------------------------------------------- #

MEDIAPIPE_MAX_FACES: int = 1
MEDIAPIPE_MIN_DETECTION_CONFIDENCE: float = 0.5
MEDIAPIPE_MIN_TRACKING_CONFIDENCE: float = 0.5
MEDIAPIPE_REFINE_LANDMARKS: bool = True   # Needed for accurate eye/iris landmarks


# --------------------------------------------------------------------------- #
# DECISION ENGINE THRESHOLDS  (the "physics" of the system)
# --------------------------------------------------------------------------- #

@dataclass
class Thresholds:
    """
    All values a driver-monitoring engineer would tune on a test bench.
    Grouped by the physical signal they act on. Each field also carries a
    human-readable `label`/`description` pair via the SETTINGS_SCHEMA below,
    which is what powers the "Scratch-style" block UI in the frontend.
    """

    # ---- Eye Aspect Ratio (EAR) ----------------------------------------- #
    # EAR drops sharply when the eyes close. A resting, open eye typically
    # measures 0.28-0.35 for most people; a fully closed eye approaches 0.05-0.12.
    ear_threshold: float = 0.25
    # Consecutive frames the EAR must stay below threshold before we trust
    # that the eye is *actually* closed (filters single-frame landmark noise).
    ear_consec_frames: int = 1

    # ---- Blink classification (based on measured closure duration) ------ #
    blink_min_duration_s: float = 0.06     # Below this = landmark jitter, not a real blink
    blink_max_duration_s: float = 0.30     # Above this = no longer a "normal" blink
    long_blink_max_duration_s: float = 1.0 # Between blink_max and this = "long blink"
    microsleep_duration_s: float = 1.0     # At/above this = microsleep -> immediate Level 3

    # ---- Blink frequency (fatigue indicator) ----------------------------- #
    blink_freq_window_s: float = 30.0      # Rolling window used to compute blinks/minute
    high_blink_freq_threshold: float = 18.0  # blinks/min above this = rapid blinking (fatigue sign)

    # ---- Long-blink accumulation (fatigue indicator) ---------------------#
    long_blink_window_s: float = 30.0
    long_blink_count_threshold: int = 2    # 2+ long blinks inside the window = fatigue sign

    # ---- Mouth Aspect Ratio (MAR) / Yawning ------------------------------ #
    mar_threshold: float = 0.55
    yawn_min_duration_s: float = 0.3       # MAR must stay above threshold this long to count as a yawn
    yawn_window_s: float = 180.0           # 3-minute rolling window
    yawn_count_threshold: int = 2          # 2+ yawns inside the window = fatigue sign

    # ---- Face presence ----------------------------------------------------#
    face_lost_warning_s: float = 1.5       # No face for this long -> show "face not visible" warning
    face_lost_critical_s: float = 3.0      # No face for this long -> escalate to urgent alert

    # ---- Fatigue score combinator ----------------------------------------#
    # We do NOT use a black-box classifier. Each indicator below contributes
    # exactly 1 point if active. If the summed score reaches the threshold,
    # the driver is classified as "Fatigue Detected" (Level 2). This keeps
    # every decision traceable to named, human-readable reasons.
    fatigue_score_threshold: int = 1

    # ---- Alerting / timing -------------------------------------------------#
    level2_alert_repeat_s: float = 5.0     # Minimum gap between repeated Level-2 chime events
    level3_alert_repeat_s: float = 2.0     # Minimum gap between repeated Level-3 alarm events

    # ---- UI ----------------------------------------------------------------#
    ui_refresh_hz: int = 15                # Target rate at which metrics are pushed to the browser


DEFAULT_THRESHOLDS = Thresholds()


# --------------------------------------------------------------------------- #
# MEDIAPIPE FACE MESH LANDMARK INDICES
# --------------------------------------------------------------------------- #
# MediaPipe Face Mesh returns 468 (or 478 with iris refinement) 3D landmarks.
# These index sets are the well-established subsets used to compute EAR/MAR.
# Reference points chosen follow the standard 6-point EAR formulation
# (Soukupova & Cech, 2016) adapted to MediaPipe's topology.

LEFT_EYE = {
    "horizontal": (33, 133),          # outer corner, inner corner
    "vertical_1": (159, 145),         # upper lid, lower lid (pair 1)
    "vertical_2": (158, 153),         # upper lid, lower lid (pair 2)
}

RIGHT_EYE = {
    "horizontal": (362, 263),
    "vertical_1": (386, 374),
    "vertical_2": (385, 380),
}

MOUTH = {
    "horizontal": (61, 291),          # left corner, right corner
    "vertical_1": (13, 14),           # inner upper lip, inner lower lip
    "vertical_2": (81, 178),
    "vertical_3": (311, 402),
}

# Full point sets used only for drawing the debug mesh overlay on the frontend
LEFT_EYE_OUTLINE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
RIGHT_EYE_OUTLINE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]
MOUTH_OUTLINE = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185]


# --------------------------------------------------------------------------- #
# SETTINGS SCHEMA (drives the frontend "Scratch-style" settings blocks)
# --------------------------------------------------------------------------- #
# Each entry describes one Threshold field in plain language so the frontend
# can render an editable "block" (slider / number / toggle) without any
# hardcoded UI copy. `kind` picks the widget: "slider", "number", "toggle".

SETTINGS_SCHEMA: list[Dict[str, Any]] = [
    {
        "key": "ear_threshold", "group": "Eyes", "kind": "slider",
        "label": "Eye Closed Threshold (EAR)",
        "description": "When the Eye Aspect Ratio drops below this value, the eye is considered closed.",
        "min": 0.10, "max": 0.35, "step": 0.01, "unit": "",
    },
    {
        "key": "microsleep_duration_s", "group": "Eyes", "kind": "slider",
        "label": "Microsleep Duration",
        "description": "If eyes stay closed at least this long, it's classified as a microsleep (Level 3).",
        "min": 0.5, "max": 4.0, "step": 0.1, "unit": "s",
    },
    {
        "key": "long_blink_max_duration_s", "group": "Eyes", "kind": "slider",
        "label": "Long Blink Upper Bound",
        "description": "Closures shorter than the microsleep duration but longer than a normal blink count as a 'long blink'.",
        "min": 0.4, "max": 3.0, "step": 0.1, "unit": "s",
    },
    {
        "key": "blink_max_duration_s", "group": "Eyes", "kind": "slider",
        "label": "Normal Blink Upper Bound",
        "description": "Closures shorter than this are counted as ordinary blinks.",
        "min": 0.1, "max": 1.0, "step": 0.05, "unit": "s",
    },
    {
        "key": "high_blink_freq_threshold", "group": "Blink Rate", "kind": "slider",
        "label": "Rapid Blinking Threshold",
        "description": "Blink rate (per minute) above this is treated as a fatigue sign.",
        "min": 10, "max": 45, "step": 1, "unit": "blinks/min",
    },
    {
        "key": "long_blink_count_threshold", "group": "Blink Rate", "kind": "number",
        "label": "Repeated Long Blinks",
        "description": "This many long blinks within a minute is treated as a fatigue sign.",
        "min": 1, "max": 10, "step": 1, "unit": "",
    },
    {
        "key": "mar_threshold", "group": "Mouth", "kind": "slider",
        "label": "Yawn Threshold (MAR)",
        "description": "When the Mouth Aspect Ratio exceeds this value, the mouth is considered open wide (yawning).",
        "min": 0.30, "max": 1.00, "step": 0.02, "unit": "",
    },
    {
        "key": "yawn_count_threshold", "group": "Mouth", "kind": "number",
        "label": "Yawns Before Fatigue Flag",
        "description": "This many yawns within 5 minutes is treated as a fatigue sign.",
        "min": 1, "max": 10, "step": 1, "unit": "",
    },
    {
        "key": "fatigue_score_threshold", "group": "Decision Engine", "kind": "number",
        "label": "Fatigue Score to Trigger Level 2",
        "description": "Number of simultaneous fatigue signs required before the system declares 'Fatigue Detected'.",
        "min": 1, "max": 4, "step": 1, "unit": "points",
    },
    {
        "key": "face_lost_warning_s", "group": "Face Presence", "kind": "slider",
        "label": "Face Lost Warning Delay",
        "description": "How long the face may be missing before a warning is shown.",
        "min": 0.5, "max": 10.0, "step": 0.5, "unit": "s",
    },
    {
        "key": "face_lost_critical_s", "group": "Face Presence", "kind": "slider",
        "label": "Face Lost Critical Delay",
        "description": "How long the face may be missing before it is treated as a critical/urgent alert.",
        "min": 1.0, "max": 20.0, "step": 0.5, "unit": "s",
    },
]


def thresholds_to_dict(t: Thresholds) -> Dict[str, Any]:
    return asdict(t)


def apply_dict_to_thresholds(t: Thresholds, data: Dict[str, Any]) -> None:
    """Mutate `t` in place with any recognised keys from `data`. Unknown keys are ignored."""
    for key, value in data.items():
        if hasattr(t, key):
            current = getattr(t, key)
            try:
                # Preserve the original type (int vs float) of each field.
                cast_value = type(current)(value)
                setattr(t, key, cast_value)
            except (TypeError, ValueError):
                continue
