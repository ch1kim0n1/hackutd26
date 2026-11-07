"""Observation dedup: collapse repeats within a window while retaining
all observation refs as evidence."""
from __future__ import annotations

from .models import NormalizedObservation


class Deduplicator:
    def __init__(self, window_s: float = 30.0):
        self.window_s = window_s
        self._last: dict[str, tuple[float, list[str]]] = {}

    def feed(self, obs: NormalizedObservation) -> tuple[bool, list[str]]:
        """Returns (is_duplicate, all_obs_ids_including_this)."""
        key = obs.dedup_key
        entry = self._last.get(key)
        if entry and obs.observed_epoch - entry[0] <= self.window_s:
            entry[1].append(obs.event_id)
            self._last[key] = (entry[0], entry[1])
            return True, entry[1]
        self._last[key] = (obs.observed_epoch, [obs.event_id])
        return False, [obs.event_id]
