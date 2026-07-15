"""
core/decision_engine.py
========================
The explainable, rule-based brain of the system.

DESIGN PHILOSOPHY
------------------
No neural network, no confidence score pulled out of thin air. Every output
of this module can be traced back to a named threshold in `config.py` and a
plain-English reason string. This is deliberate: a driver-safety feature
that can't explain *why* it fired an alarm is not trustworthy, and is a hard
sell to both judges and, hypothetically, regulators.

THE MODEL
---------
Two independent state machines run every frame:

  1. Eye-closure tracker
     Watches EAR crossing `ear_threshold`. While the eye is closed it keeps
     a live "current closure duration". When the eye re-opens, the finished
     closure is classified as one of:
         - noise            (< blink_min_duration_s)          -> discarded
         - normal blink      (blink_min .. blink_max)          -> counted
         - long blink         (blink_max .. microsleep)         -> counted + flagged
     If the eye is STILL closed and current duration has already reached
     `microsleep_duration_s`, we don't wait for it to re-open — we declare
     a microsleep immediately, in real time.

  2. Mouth-open (yawn) tracker
     Symmetric idea: MAR crossing `mar_threshold`. A completed open interval
     longer than `yawn_min_duration_s` is counted as a yawn.

Both trackers feed rolling time windows (blink frequency, long-blink count,
yawn count) which are the raw ingredients of the "Fatigue Score" below.

THE FATIGUE SCORE
------------------
A simple, fully transparent point system. Each of the following, if
currently true, contributes exactly +1 point:

    [1] Eyes are currently in a long, slow closure (not yet a microsleep)
    [2] Blink frequency over the last N seconds is abnormally high
    [3] There have been several long blinks recently
    [4] There have been several yawns recently

If the total score reaches `fatigue_score_threshold` (default: 2 — i.e. at
least two independent signs agreeing at once), the driver is classified as
"Fatigue Detected". This avoids false positives from any single noisy signal
while staying 100% explainable ("two of four fatigue signs are active").

THE FINAL STATE MACHINE  (evaluated in this priority order every frame)
-------------------------------------------------------------------------
    1. FACE_NOT_DETECTED   - can't assess a driver we can't see
    2. SLEEPING             - microsleep in progress (eyes closed too long)
    3. FATIGUE               - fatigue score >= threshold
    4. SAFE                   - otherwise
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, List, Optional

from backend.config import Thresholds


class DriverState(str, Enum):
    SAFE = "SAFE"
    FATIGUE = "FATIGUE"
    SLEEPING = "SLEEPING"
    FACE_NOT_DETECTED = "FACE_NOT_DETECTED"


# Level number kept for the frontend (matches the spec's Level 1/2/3),
# FACE_NOT_DETECTED is treated as its own lane but mapped to level 0 so the
# UI can still pick an appropriate (neutral/urgent) color for it.
STATE_LEVEL = {
    DriverState.SAFE: 1,
    DriverState.FATIGUE: 2,
    DriverState.SLEEPING: 3,
    DriverState.FACE_NOT_DETECTED: 0,
}

STATE_COLOR = {
    DriverState.SAFE: "#3ecf8e",             # emerald green
    DriverState.FATIGUE: "#e8a13a",          # amber
    DriverState.SLEEPING: "#e5484d",         # red
    DriverState.FACE_NOT_DETECTED: "#8a8f98",  # neutral grey
}


@dataclass
class DecisionSnapshot:
    """Everything the frontend needs to render one frame of dashboard state."""
    timestamp: float
    state: str
    level: int
    color: str
    reasons: List[str]

    ear: float
    mar: float
    left_ear: float
    right_ear: float

    face_visible: bool
    face_lost_duration_s: float

    eye_closed: bool
    current_eye_closure_s: float

    blink_count_total: int
    blink_frequency_per_min: float
    long_blink_count_window: int

    yawn_count_total: int
    yawn_count_window: int

    fatigue_score: int
    fatigue_score_threshold: int

    last_event: Optional[str] = None  # e.g. "BLINK", "LONG_BLINK", "MICROSLEEP", "YAWN"


class DecisionEngine:
    """
    Stateful, per-session engine. One instance per active monitoring session.
    Call `update(ear, mar, face_detected)` once per processed frame.
    """

    def __init__(self, thresholds: Thresholds) -> None:
        self.thresholds = thresholds  # NOTE: shared reference -> live-tunable from Settings panel

        # Eye-closure tracking
        self._eye_closed: bool = False
        self._eye_closed_since: Optional[float] = None
        self._consec_closed_frames: int = 0

        # Mouth-open tracking
        self._mouth_open: bool = False
        self._mouth_open_since: Optional[float] = None

        # Face presence tracking
        self._face_lost_since: Optional[float] = None

        # Rolling event windows (store timestamps only)
        self._blink_events: Deque[float] = deque()
        self._long_blink_events: Deque[float] = deque()
        self._yawn_events: Deque[float] = deque()

        # Lifetime counters (for dashboard display, never pruned)
        self.total_blinks: int = 0
        self.total_yawns: int = 0

        self.session_start = time.time()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def update(
        self,
        ear: float,
        mar: float,
        face_detected: bool,
        left_ear: Optional[float] = None,
        right_ear: Optional[float] = None,
        now: Optional[float] = None,
    ) -> DecisionSnapshot:
        now = now if now is not None else time.time()
        t = self.thresholds
        last_event: Optional[str] = None

        # ---- Face presence ------------------------------------------- #
        if face_detected:
            self._face_lost_since = None
        else:
            if self._face_lost_since is None:
                self._face_lost_since = now
        face_lost_duration = (now - self._face_lost_since) if self._face_lost_since else 0.0

        # ---- Eye closure state machine (only meaningful if face seen) - #
        current_eye_closure = 0.0
        if face_detected:
            eye_closed_now = ear < t.ear_threshold
            if eye_closed_now:
                self._consec_closed_frames += 1
            else:
                self._consec_closed_frames = 0

            confirmed_closed = self._consec_closed_frames >= max(1, t.ear_consec_frames)

            if confirmed_closed and not self._eye_closed:
                # Transition: open -> closed
                self._eye_closed = True
                self._eye_closed_since = now

            elif (not confirmed_closed) and self._eye_closed:
                # Transition: closed -> open. Classify the finished closure.
                duration = now - (self._eye_closed_since or now)
                self._eye_closed = False
                self._eye_closed_since = None

                if duration < t.blink_min_duration_s:
                    pass  # noise, discard
                elif duration <= t.blink_max_duration_s:
                    self.total_blinks += 1
                    self._blink_events.append(now)
                    last_event = "BLINK"
                elif duration < t.microsleep_duration_s:
                    self.total_blinks += 1
                    self._long_blink_events.append(now)
                    last_event = "LONG_BLINK"
                else:
                    last_event = "MICROSLEEP_END"

            if self._eye_closed and self._eye_closed_since is not None:
                current_eye_closure = now - self._eye_closed_since
        else:
            # No face -> eye state is unknown/meaningless; don't accumulate.
            self._eye_closed = False
            self._eye_closed_since = None
            self._consec_closed_frames = 0

        # ---- Mouth / yawn state machine -------------------------------#
        if face_detected:
            mouth_open_now = mar > t.mar_threshold
            if mouth_open_now and not self._mouth_open:
                self._mouth_open = True
                self._mouth_open_since = now
            elif (not mouth_open_now) and self._mouth_open:
                duration = now - (self._mouth_open_since or now)
                self._mouth_open = False
                self._mouth_open_since = None
                if duration >= t.yawn_min_duration_s:
                    self.total_yawns += 1
                    self._yawn_events.append(now)
                    last_event = last_event or "YAWN"

        # ---- Prune rolling windows -------------------------------------#
        self._prune(self._blink_events, now, t.blink_freq_window_s)
        self._prune(self._long_blink_events, now, t.long_blink_window_s)
        self._prune(self._yawn_events, now, t.yawn_window_s)

        blink_frequency = len(self._blink_events) * (60.0 / t.blink_freq_window_s)
        long_blink_count_window = len(self._long_blink_events)
        yawn_count_window = len(self._yawn_events)

        # ------------------------------------------------------------------ #
        # DECISION: evaluate rules in strict priority order
        # ------------------------------------------------------------------ #
        state = DriverState.SAFE
        reasons: List[str] = []
        fatigue_score = 0

        if (not face_detected) and face_lost_duration >= t.face_lost_warning_s:
            state = DriverState.FACE_NOT_DETECTED
            urgency = "critical" if face_lost_duration >= t.face_lost_critical_s else "warning"
            reasons = [f"No face detected for {face_lost_duration:.1f}s ({urgency})"]

        elif face_detected and current_eye_closure >= t.microsleep_duration_s:
            state = DriverState.SLEEPING
            reasons = [
                f"Eyes closed for {current_eye_closure:.1f}s "
                f"(>= microsleep threshold {t.microsleep_duration_s:.1f}s)"
            ]

        elif face_detected:
            # Build the fatigue score from independent, named indicators.
            if current_eye_closure >= t.blink_max_duration_s:
                fatigue_score += 1
                reasons.append(f"Eyes currently closing slowly ({current_eye_closure:.2f}s)")

            if blink_frequency >= t.high_blink_freq_threshold:
                fatigue_score += 1
                reasons.append(f"Rapid blinking ({blink_frequency:.0f} blinks/min)")

            if long_blink_count_window >= t.long_blink_count_threshold:
                fatigue_score += 1
                reasons.append(
                    f"{long_blink_count_window} long blinks in the last "
                    f"{int(t.long_blink_window_s)}s"
                )

            if yawn_count_window >= t.yawn_count_threshold:
                fatigue_score += 1
                reasons.append(
                    f"{yawn_count_window} yawns in the last "
                    f"{int(t.yawn_window_s // 60)} min"
                )

            if fatigue_score >= t.fatigue_score_threshold:
                state = DriverState.FATIGUE
            else:
                state = DriverState.SAFE
                if not reasons:
                    reasons = ["All indicators within normal range"]
                else:
                    # Sub-threshold: still show what's building up, prefixed clearly.
                    reasons = [f"Monitoring: {r}" for r in reasons]

        else:
            reasons = ["Face not yet detected"]

        return DecisionSnapshot(
            timestamp=now,
            state=state.value,
            level=STATE_LEVEL[state],
            color=STATE_COLOR[state],
            reasons=reasons,
            ear=round(ear, 4),
            mar=round(mar, 4),
            left_ear=round(left_ear if left_ear is not None else ear, 4),
            right_ear=round(right_ear if right_ear is not None else ear, 4),
            face_visible=face_detected,
            face_lost_duration_s=round(face_lost_duration, 2),
            eye_closed=self._eye_closed,
            current_eye_closure_s=round(current_eye_closure, 2),
            blink_count_total=self.total_blinks,
            blink_frequency_per_min=round(blink_frequency, 1),
            long_blink_count_window=long_blink_count_window,
            yawn_count_total=self.total_yawns,
            yawn_count_window=yawn_count_window,
            fatigue_score=fatigue_score,
            fatigue_score_threshold=t.fatigue_score_threshold,
            last_event=last_event,
        )

    def acknowledge(self) -> None:
        """Driver pressed 'I am awake'. Clears all fatigue indicators and
        resets the eye/mouth state machines so the system starts fresh,
        but preserves lifetime counters (total blinks, total yawns)."""
        self._eye_closed = False
        self._eye_closed_since = None
        self._consec_closed_frames = 0

        self._mouth_open = False
        self._mouth_open_since = None

        self._blink_events.clear()
        self._long_blink_events.clear()
        self._yawn_events.clear()

    def reset(self) -> None:
        """Start a brand-new session (clears counters and timers)."""
        self.__init__(self.thresholds)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _prune(events: Deque[float], now: float, window_s: float) -> None:
        while events and (now - events[0]) > window_s:
            events.popleft()
