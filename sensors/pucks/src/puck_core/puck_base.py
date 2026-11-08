"""Shared puck base: seq numbering, signing, health, LED intent."""
from __future__ import annotations

import time
from typing import Callable

from .auth import sign
from .inventory import Inventory
from .models import EventKind, HealthStatus, Observation, utc_now_iso


class PuckBase:
    puck_type: str = ""

    def __init__(self, device_id: str, zone_id: str, secret: bytes,
                 inventory: Inventory, clock: Callable[[], float] = time.time,
                 transport=None):
        self.device_id = device_id
        self.zone_id = zone_id
        self.secret = secret
        self.inventory = inventory
        self.clock = clock
        # Optional Transport (see transport.py) — ConsoleTransport for bench,
        # MqttTransport for the live Sentinel Hive uplink.
        self.transport = transport
        self.seq = 0
        self.health = HealthStatus.OK
        self._health_note = ""
        self.events: list[Observation] = []

    def _next_seq(self) -> int:
        self.seq += 1
        return self.seq

    def emit(self, kind, data: dict) -> Observation:
        obs = Observation(
            device_id=self.device_id,
            seq=self._next_seq(),
            observed_at=utc_now_iso(),
            kind=kind,
            zone_id=self.zone_id,
            data=data,
        )
        obs.signature = sign(self.secret, obs)
        self.events.append(obs)
        if self.transport is not None:
            try:
                self.transport.publish(obs)
            except Exception:
                # telemetry loss must not crash the sensing loop; the
                # gateway dedupes/rejects replays server-side anyway
                pass
        return obs

    def health_event(self, status: HealthStatus, note: str = "") -> Observation:
        self.health = status
        self._health_note = note
        return self.emit(
            EventKind.DEVICE_HEALTH,
            {"status": status.value, "note": note, "firmware": "puck-fw-0.1"},
        )

    @property
    def led_state(self) -> str:
        return {
            HealthStatus.OK: "solid_green",
            HealthStatus.DEGRADED: "blink_amber",
            HealthStatus.STALE: "blink_amber",
            HealthStatus.OFFLINE: "off",
        }[self.health]
