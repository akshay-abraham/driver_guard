"""
vision/face_processor.py
=========================
Thin, defensive wrapper around Google MediaPipe Face Mesh.

Responsibilities:
    1. Run face-mesh inference on a BGR frame.
    2. Convert normalised landmarks -> pixel coordinates.
    3. Draw a minimal, purposeful debug overlay (eye/mouth outline only —
       not all 468 points, which would look like noise) so the video feed
       itself explains what the system is measuring.

This module has ZERO knowledge of thresholds or decision logic — it only
ever reports raw geometry. That separation is what keeps the decision engine
testable and the vision pipeline swappable.

BACKEND COMPATIBILITY
----------------------
Google has been migrating MediaPipe from the classic "Solutions" API
(`mediapipe.solutions.face_mesh`) to the newer "Tasks" API
(`mediapipe.tasks.python.vision.FaceLandmarker`). Depending on exactly which
`mediapipe` wheel gets installed, only one of the two may be available. Both
return landmarks over the *same* 468/478-point face topology, so the rest of
the pipeline (config.py landmark indices, metrics.py) works unchanged either
way. We therefore try the classic Solutions API first (zero extra downloads,
what most tutorials/hackathon setups expect) and transparently fall back to
the Tasks API (auto-downloading its small model file on first run) if
Solutions isn't present in the installed package.
"""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Protocol, Tuple

import cv2
import numpy as np

from backend.config import (
    MEDIAPIPE_MAX_FACES,
    MEDIAPIPE_MIN_DETECTION_CONFIDENCE,
    MEDIAPIPE_MIN_TRACKING_CONFIDENCE,
    MEDIAPIPE_REFINE_LANDMARKS,
    LEFT_EYE_OUTLINE,
    RIGHT_EYE_OUTLINE,
    MOUTH_OUTLINE,
)

Point = Tuple[float, float]

_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
_MODEL_CACHE_PATH = Path(__file__).resolve().parents[2] / "models" / "face_landmarker.task"


@dataclass
class FaceMeshResult:
    """Everything downstream code needs from a single processed frame."""
    face_detected: bool
    landmarks: Optional[List[Point]]      # pixel-space (x, y) for every landmark, or None
    frame_width: int
    frame_height: int


class _Backend(Protocol):
    def infer(self, frame_rgb: np.ndarray, width: int, height: int) -> Optional[List[Point]]: ...
    def close(self) -> None: ...


class _SolutionsBackend:
    """Classic `mediapipe.solutions.face_mesh` backend."""

    def __init__(self) -> None:
        import mediapipe as mp  # local import: only touched if this backend is chosen

        self._face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=MEDIAPIPE_MAX_FACES,
            refine_landmarks=MEDIAPIPE_REFINE_LANDMARKS,
            min_detection_confidence=MEDIAPIPE_MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=MEDIAPIPE_MIN_TRACKING_CONFIDENCE,
        )

    def infer(self, frame_rgb: np.ndarray, width: int, height: int) -> Optional[List[Point]]:
        results = self._face_mesh.process(frame_rgb)
        if not results.multi_face_landmarks:
            return None
        face = results.multi_face_landmarks[0]
        return [(lm.x * width, lm.y * height) for lm in face.landmark]

    def close(self) -> None:
        self._face_mesh.close()


class _TasksBackend:
    """Newer `mediapipe.tasks.python.vision.FaceLandmarker` backend."""

    def __init__(self) -> None:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision

        model_path = self._ensure_model()

        base_options = mp_python.BaseOptions(model_asset_path=str(model_path))
        options = mp_vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=mp_vision.RunningMode.IMAGE,
            num_faces=MEDIAPIPE_MAX_FACES,
            min_face_detection_confidence=MEDIAPIPE_MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=MEDIAPIPE_MIN_TRACKING_CONFIDENCE,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
        )
        self._mp_image_cls = mp.Image
        self._image_format = mp.ImageFormat.SRGB
        self._landmarker = mp_vision.FaceLandmarker.create_from_options(options)

    @staticmethod
    def _ensure_model() -> Path:
        if _MODEL_CACHE_PATH.exists():
            return _MODEL_CACHE_PATH
        _MODEL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            urllib.request.urlretrieve(_MODEL_URL, _MODEL_CACHE_PATH)
        except Exception as exc:  # noqa: BLE001 - want a clear actionable message
            raise RuntimeError(
                "Could not download the MediaPipe Face Landmarker model "
                f"(needed because this mediapipe build has no 'solutions' API). "
                f"Download it manually from:\n  {_MODEL_URL}\n"
                f"and place it at:\n  {_MODEL_CACHE_PATH}"
            ) from exc
        return _MODEL_CACHE_PATH

    def infer(self, frame_rgb: np.ndarray, width: int, height: int) -> Optional[List[Point]]:
        mp_image = self._mp_image_cls(image_format=self._image_format, data=frame_rgb)
        result = self._landmarker.detect(mp_image)
        if not result.face_landmarks:
            return None
        face = result.face_landmarks[0]
        return [(lm.x * width, lm.y * height) for lm in face]

    def close(self) -> None:
        self._landmarker.close()


def _build_backend() -> _Backend:
    try:
        return _SolutionsBackend()
    except AttributeError:
        # mediapipe installed without the legacy `solutions` package
        return _TasksBackend()


class FaceProcessor:
    """
    Backend-agnostic face-mesh processor. Picks the best available MediaPipe
    API at construction time and exposes a single stable `.process()` call.
    Must be `.close()`d — implements the context-manager protocol so callers
    can't forget.
    """

    def __init__(self) -> None:
        self._backend = _build_backend()

    def process(self, frame_bgr: np.ndarray) -> FaceMeshResult:
        """Run inference on one BGR frame and return pixel-space landmarks."""
        height, width = frame_bgr.shape[:2]
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        frame_rgb = np.ascontiguousarray(frame_rgb)

        landmarks = self._backend.infer(frame_rgb, width, height)

        return FaceMeshResult(
            face_detected=landmarks is not None,
            landmarks=landmarks,
            frame_width=width,
            frame_height=height,
        )

    def close(self) -> None:
        self._backend.close()

    def __enter__(self) -> "FaceProcessor":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def draw_overlay(
    frame_bgr: np.ndarray,
    landmarks: Optional[List[Point]],
    color_bgr: Tuple[int, int, int],
    eyes_closed: bool,
) -> np.ndarray:
    """
    Draws only the eye and mouth contours (never the full 468-point mesh —
    that reads as visual noise, not information) in the current status
    color, so the live feed itself is a live explanation of what's tracked.
    """
    if landmarks is None:
        return frame_bgr

    def polyline(indices: List[int], closed: bool = True) -> None:
        pts = np.array([landmarks[i] for i in indices], dtype=np.int32)
        cv2.polylines(frame_bgr, [pts], isClosed=closed, color=color_bgr, thickness=1, lineType=cv2.LINE_AA)

    polyline(LEFT_EYE_OUTLINE)
    polyline(RIGHT_EYE_OUTLINE)
    polyline(MOUTH_OUTLINE)

    return frame_bgr
