"""
main.py - application entry point
FastAPI application entry point.

Responsibilities:
    * Own the webcam and MediaPipe Face Mesh lifecycle (opened once at
      startup, released cleanly at shutdown — no per-request re-init).
    * Run the capture -> feature-extraction -> decision loop on a background
      thread (OpenCV/MediaPipe calls are blocking; keeping them off the
      asyncio event loop keeps the WebSocket responsive).
    * Broadcast the latest annotated frame + full metrics snapshot to every
      connected browser over a WebSocket, at a configurable UI refresh rate.
    * Expose a tiny REST surface for reading/writing the live threshold
      configuration (used by the Settings panel) and resetting the session.

The backend does ALL computer vision. The frontend only ever receives
already-computed numbers, a JPEG frame, and discrete alert events — it does
not run any vision code itself.
"""

from __future__ import annotations

import asyncio
import base64
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.config import (
    Thresholds,
    DEFAULT_THRESHOLDS,
    SETTINGS_SCHEMA,
    STREAM_MAX_WIDTH,
    JPEG_QUALITY,
)
from backend.core.decision_engine import DecisionEngine
from backend.core.alert_manager import AlertManager
from backend.schemas import ConfigUpdateRequest, SessionControlRequest
from backend.vision.camera import Camera
from backend.vision.face_processor import FaceProcessor, draw_overlay
from backend.vision.metrics import compute_ear, compute_mar

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


# --------------------------------------------------------------------------- #
# Shared, thread-safe application state
# --------------------------------------------------------------------------- #

class AppState:
    """
    Holds everything that needs to survive across requests / the background
    thread. A single lock protects the mutable fields that are written by
    the capture thread and read by the WebSocket broadcaster (and vice versa
    for threshold edits coming from the REST API).
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()

        # Thresholds is intentionally a *fresh* instance (not the module
        # default) so runtime edits never mutate the importable default.
        self.thresholds = Thresholds(**asdict(DEFAULT_THRESHOLDS))

        self.decision_engine = DecisionEngine(self.thresholds)
        self.alert_manager = AlertManager(self.thresholds)

        self.camera: Optional[Camera] = None
        self.face_processor: Optional[FaceProcessor] = None

        self.session_start = time.time()
        self.camera_error: Optional[str] = None

        # Latest broadcastable payload, written by the capture thread.
        self.latest_frame_b64: Optional[str] = None
        self.latest_snapshot: Optional[dict] = None
        self.latest_alert_event: Optional[str] = None

        # Measured FPS (rolling window of frame timestamps).
        self._frame_times: deque[float] = deque(maxlen=60)

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---------------------------------------------------------------- #

    def start(self) -> None:
        self.camera = Camera()
        if not self.camera.is_opened:
            self.camera_error = (
                "Could not open the webcam. If you're running under WSL, make sure "
                "usbipd-win has attached the camera to this WSL instance. On Fedora, "
                "check that no other application is using /dev/video0 and that your "
                "user has permission (video group)."
            )
        self.face_processor = FaceProcessor()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="dms-capture")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self.camera is not None:
            self.camera.release()
        if self.face_processor is not None:
            self.face_processor.close()

    def reset_session(self) -> None:
        with self.lock:
            self.decision_engine.reset()
            self.alert_manager = AlertManager(self.thresholds)
            self.session_start = time.time()

    def wake_up(self) -> None:
        """Driver acknowledged alert — clear fatigue indicators, suppress
        repeated alerts for a short cooldown, but keep session counters."""
        now = time.time()
        with self.lock:
            self.decision_engine.acknowledge()
            self.alert_manager.acknowledge(now)
            self.latest_alert_event = None

    def measured_fps(self) -> float:
        if len(self._frame_times) < 2:
            return 0.0
        span = self._frame_times[-1] - self._frame_times[0]
        if span <= 0:
            return 0.0
        return (len(self._frame_times) - 1) / span

    # ---------------------------------------------------------------- #
    # Background thread: capture -> vision -> decision -> encode
    # ---------------------------------------------------------------- #

    def _capture_loop(self) -> None:
        while not self._stop_event.is_set():
            if self.camera is None or not self.camera.is_opened:
                time.sleep(0.5)
                continue

            ok, frame = self.camera.read()
            if not ok or frame is None:
                time.sleep(0.05)
                continue

            now = time.time()
            self._frame_times.append(now)

            result = self.face_processor.process(frame)  # type: ignore[union-attr]

            ear = mar = 0.0
            left_ear = right_ear = 0.0
            if result.face_detected and result.landmarks is not None:
                left_ear, right_ear, ear = compute_ear(result.landmarks)
                mar = compute_mar(result.landmarks)

            with self.lock:
                snapshot = self.decision_engine.update(
                    ear=ear,
                    mar=mar,
                    face_detected=result.face_detected,
                    left_ear=left_ear,
                    right_ear=right_ear,
                    now=now,
                )
                alert_event = self.alert_manager.evaluate(snapshot.state, now)
                session_elapsed = now - self.session_start

            # ---- Draw the minimal, purposeful debug overlay ----------- #
            color_hex = snapshot.color.lstrip("#")
            color_bgr = tuple(int(color_hex[i : i + 2], 16) for i in (4, 2, 0))
            annotated = draw_overlay(frame, result.landmarks, color_bgr, snapshot.eye_closed)

            if not result.face_detected:
                cv2.putText(
                    annotated, "NO FACE DETECTED", (16, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (90, 90, 220), 2, cv2.LINE_AA,
                )

            # Downscale for bandwidth before JPEG encoding.
            h, w = annotated.shape[:2]
            if w > STREAM_MAX_WIDTH:
                scale = STREAM_MAX_WIDTH / w
                annotated = cv2.resize(annotated, (STREAM_MAX_WIDTH, int(h * scale)))

            ok_enc, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            frame_b64 = base64.b64encode(buf.tobytes()).decode("ascii") if ok_enc else None

            snapshot_dict = asdict(snapshot)
            snapshot_dict["session_elapsed_s"] = round(session_elapsed, 1)
            snapshot_dict["fps"] = round(self.measured_fps(), 1)

            with self.lock:
                self.latest_frame_b64 = frame_b64
                self.latest_snapshot = snapshot_dict
                self.latest_alert_event = alert_event


state = AppState()


# --------------------------------------------------------------------------- #
# FastAPI app + lifespan
# --------------------------------------------------------------------------- #

@asynccontextmanager
async def lifespan(app: FastAPI):
    state.start()
    try:
        yield
    finally:
        state.stop()


app = FastAPI(title="Driver Monitoring System", lifespan=lifespan)

app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/config")
async def get_config() -> JSONResponse:
    with state.lock:
        values = asdict(state.thresholds)
    return JSONResponse({"values": values, "schema": SETTINGS_SCHEMA})


@app.post("/api/config")
async def update_config(body: ConfigUpdateRequest) -> JSONResponse:
    from backend.config import apply_dict_to_thresholds

    with state.lock:
        apply_dict_to_thresholds(state.thresholds, body.values)
        values = asdict(state.thresholds)
    return JSONResponse({"values": values})


@app.post("/api/config/reset")
async def reset_config() -> JSONResponse:
    with state.lock:
        state.thresholds.__dict__.update(asdict(DEFAULT_THRESHOLDS))
        values = asdict(state.thresholds)
    return JSONResponse({"values": values})


@app.post("/api/session")
async def session_control(body: SessionControlRequest) -> JSONResponse:
    if body.action == "reset":
        state.reset_session()
        return JSONResponse({"ok": True})
    if body.action == "awake":
        state.wake_up()
        return JSONResponse({"ok": True})
    return JSONResponse({"ok": False, "error": f"Unknown action '{body.action}'"}, status_code=400)


@app.get("/api/status")
async def status() -> JSONResponse:
    return JSONResponse({
        "camera_ok": bool(state.camera and state.camera.is_opened),
        "camera_error": state.camera_error,
    })


@app.websocket("/ws")
async def ws_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            with state.lock:
                refresh_hz = max(1, state.thresholds.ui_refresh_hz)
                payload = {
                    "type": "frame",
                    "frame": state.latest_frame_b64,
                    "metrics": state.latest_snapshot,
                    "alert_event": state.latest_alert_event,
                    "camera_ok": bool(state.camera and state.camera.is_opened),
                    "camera_error": state.camera_error,
                }
                # Alert events are one-shot: clear after broadcasting once.
                state.latest_alert_event = None

            await websocket.send_json(payload)
            await asyncio.sleep(1.0 / refresh_hz)
    except WebSocketDisconnect:
        pass


if __name__ == "__main__":
    import uvicorn
    from backend.config import SERVER_HOST, SERVER_PORT

    uvicorn.run("backend.main:app", host=SERVER_HOST, port=SERVER_PORT, reload=False)
