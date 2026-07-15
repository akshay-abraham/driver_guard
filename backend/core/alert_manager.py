"""
core/alert_manager.py
======================
The DecisionEngine reports a *continuous* state every frame (e.g. "SLEEPING"
for as long as the eyes stay shut). The frontend, however, should not be told
to (re)start an alarm sound 15 times a second — it needs discrete *events*:
"fire the Level 3 alarm now", then silence until it's appropriate to repeat.

This module is the bridge: it watches the DecisionEngine's state stream and
emits a throttled `alert_event` (or None) alongside every snapshot, using the
`level2_alert_repeat_s` / `level3_alert_repeat_s` cooldowns from config. All
audio/visual playback itself lives entirely in the browser (per the
cross-platform requirement) — this module only decides *when* to ask for it.
"""

from __future__ import annotations

from typing import Optional

from backend.config import Thresholds
from backend.core.decision_engine import DriverState


class AlertManager:
    def __init__(self, thresholds: Thresholds) -> None:
        self.thresholds = thresholds
        self._last_state: Optional[str] = None
        self._last_fire_time: dict[str, float] = {}
        self._suppress_until: float = 0.0  # after acknowledge(), no alerts until this time

    def acknowledge(self, now: float) -> None:
        """Suppress all alerts for 10 seconds after the driver says 'I am awake'."""
        self._suppress_until = now + 10.0

    def evaluate(self, state: str, now: float) -> Optional[str]:
        """
        Returns one of: "LEVEL2_ALERT", "LEVEL3_ALARM", "FACE_WARNING", or None.

        Rule: always fire immediately on entering a new alert-worthy state
        (so the driver is warned the instant it happens), then repeat at the
        configured cooldown interval for as long as the state persists.
        """
        if now < self._suppress_until:
            self._last_state = state
            return None

        t = self.thresholds
        event: Optional[str] = None

        cooldowns = {
            DriverState.FATIGUE.value: t.level2_alert_repeat_s,
            DriverState.SLEEPING.value: t.level3_alert_repeat_s,
            DriverState.FACE_NOT_DETECTED.value: t.level2_alert_repeat_s,
        }
        event_names = {
            DriverState.FATIGUE.value: "LEVEL2_ALERT",
            DriverState.SLEEPING.value: "LEVEL3_ALARM",
            DriverState.FACE_NOT_DETECTED.value: "FACE_WARNING",
        }

        if state in cooldowns:
            state_changed = state != self._last_state
            last_fire = self._last_fire_time.get(state, -1e9)
            due = (now - last_fire) >= cooldowns[state]
            if state_changed or due:
                event = event_names[state]
                self._last_fire_time[state] = now

        self._last_state = state
        return event
