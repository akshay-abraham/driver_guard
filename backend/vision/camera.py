"""
vision/camera.py
=================
Thin wrapper around cv2.VideoCapture with explicit resource management and
sane cross-platform defaults (Fedora / Windows / WSL-Fedora).

WSL note: WSL does not have native access to a physical webcam unless a
USB/IP passthrough (usbipd-win) has been set up. If the camera fails to
open under WSL, `is_opened` will be False and the API surfaces a clear
error to the frontend instead of silently hanging.
"""

from __future__ import annotations

import platform
from typing import Optional, Tuple

import cv2
import numpy as np

from backend.config import CAMERA_INDEX, CAMERA_WIDTH, CAMERA_HEIGHT, CAMERA_FPS_TARGET


def _preferred_backend() -> int:
    """Pick a VideoCapture backend that behaves well on the current OS."""
    system = platform.system().lower()
    if system == "windows":
        return cv2.CAP_DSHOW
    # Linux (Fedora / WSL-Fedora) - default V4L2 backend
    return cv2.CAP_V4L2 if hasattr(cv2, "CAP_V4L2") else cv2.CAP_ANY


class Camera:
    """Context-manager friendly webcam capture."""

    def __init__(self, index: int = CAMERA_INDEX) -> None:
        self.index = index
        self._cap: Optional[cv2.VideoCapture] = None
        self.is_opened: bool = False
        self.open()

    def open(self) -> None:
        backend = _preferred_backend()
        cap = cv2.VideoCapture(self.index, backend)
        if not cap.isOpened():
            # Fallback: let OpenCV auto-pick a backend.
            cap = cv2.VideoCapture(self.index)

        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
            cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS_TARGET)
            # Keep the internal buffer small so we always read a fresh frame.
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self._cap = cap
        self.is_opened = cap.isOpened()

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if not self.is_opened or self._cap is None:
            return False, None
        ok, frame = self._cap.read()
        if not ok:
            return False, None
        # Mirror the frame horizontally -> feels like a natural "look at yourself" mirror.
        frame = cv2.flip(frame, 1)
        return True, frame

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self.is_opened = False

    def __enter__(self) -> "Camera":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()
