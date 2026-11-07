"""Puck B — cabinet reed switch with debounce and maintenance-window semantics.

Raw GPIO samples go through debounce_stable_s of unchanged level before a
transition is accepted. Open events carry authorized=true only inside an
inventory maintenance window for this zone; otherwise authorized=false —
the correlator turns that into PHY01 evidence (docs/03)."""
from __future__ import annotations

from .models import EventKind, utc_now_iso
from .puck_base import PuckBase


class CabinetPuck(PuckBase):
    puck_type = "puck-b"

    def __init__(self, *args, debounce_s: float = 0.05,
                 sample_period_s: float = 0.01, **kwargs):
        super().__init__(*args, **kwargs)
        self.debounce_s = debounce_s
        self.sample_period_s = sample_period_s
        self._raw = False          # last raw level (True = closed/magnet near)
        self._stable = False       # debounced level
        self._pending = False      # candidate level
        self._pending_since = 0.0
        self._initialized = False

    def sample(self, raw_closed: bool, now: float | None = None) -> list:
        """Feed one GPIO sample. Returns emitted events (0 or 1)."""
        now = self.clock() if now is None else now
        if not self._initialized:
            self._raw = self._stable = self._pending = raw_closed
            self._pending_since = now
            self._initialized = True
            return []
        if raw_closed == self._pending:
            if raw_closed != self._stable and now - self._pending_since >= self.debounce_s:
                self._stable = raw_closed
                return self._transition(now)
            return []
        # level changed: start pending window
        self._pending = raw_closed
        self._pending_since = now
        return []

    def _transition(self, now: float) -> list:
        closed = self._stable
        iso = utc_now_iso()
        in_window = self.inventory.maintenance_active(self.zone_id, iso)
        if closed:
            obs = self.emit(EventKind.CABINET_CONTACT_CLOSED, {
                "contact": "closed",
                "authorized": True,  # closing is never anomalous
                "maintenance_window": in_window,
            })
        else:
            obs = self.emit(EventKind.CABINET_CONTACT_OPEN, {
                "contact": "open",
                "authorized": in_window,  # PHY01 input: open outside window
                "maintenance_window": in_window,
                "maintenance_authorized_by": next(
                    (w.authorized_by for w in self.inventory.maintenance_windows
                     if w.covers(self.zone_id, iso)), None),
            })
        return [obs]
