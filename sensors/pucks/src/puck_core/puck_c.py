"""Puck C — BLE observer restricted to enrolled lab beacons.

Non-enrolled advertisements are counted but NEVER emitted as events and no
identifiers are retained — no people tracking, no BLE fingerprinting
(docs/03, charter P2 exclusions)."""
from __future__ import annotations

from .models import EventKind
from .puck_base import PuckBase

DEDUP_WINDOW_S = 10.0


class BlePuck(PuckBase):
    puck_type = "puck-c"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_seen: dict[str, float] = {}
        self.dropped_unenrolled = 0

    def observe(self, address: str | None, rssi_dbm: int,
                service_uuid: str | None = None,
                device_name: str | None = None) -> list:
        """One BLE advertisement. Returns emitted events (0 or 1)."""
        if not self.inventory.is_enrolled_beacon(address, service_uuid):
            self.dropped_unenrolled += 1
            return []
        key = (address or "").lower() or (service_uuid or "").lower()
        now = self.clock()
        last = self._last_seen.get(key)
        if last is not None and now - last < DEDUP_WINDOW_S:
            return []
        self._last_seen[key] = now
        obs = self.emit(EventKind.BLE_BEACON_SEEN, {
            "beacon_key": key,
            "address": (address or "").lower() or None,
            "service_uuid": service_uuid,
            "rssi_dbm": int(rssi_dbm),
            "enrolled": True,
        })
        return [obs]
