"""Collector-side authenticated ingest + device health/staleness.

This is the receiving half of 'authenticated observations': the gateway/
collector validates schema, signature, per-device sequence monotonicity,
kind-vs-device-type and known devices — per docs/04 gateway rules.
It does NOT authorize anything; it only admits well-formed evidence."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from .auth import verify
from .models import (
    MAX_PACKET_BYTES,
    EventKind,
    HealthStatus,
    Observation,
    PUCK_KINDS,
    utc_now_iso,
)


@dataclass
class DeviceRecord:
    device_id: str
    puck_type: str           # puck-a | puck-b | puck-c
    zone_id: str
    secret: bytes
    last_seq: int = 0
    last_seen: float = 0.0
    status: HealthStatus = HealthStatus.STALE
    last_health_note: str = ""


@dataclass
class IngestResult:
    ok: bool
    reason: str
    observation: Observation | None = None


class Collector:
    def __init__(self, stale_after_s: float = 30.0,
                 clock: Callable[[], float] = time.time):
        self.devices: dict[str, DeviceRecord] = {}
        self.stale_after_s = stale_after_s
        self.clock = clock
        self.accepted: list[Observation] = []
        self.rejected: list[tuple[str, str]] = []  # (device_id, reason)

    def register(self, device_id: str, puck_type: str, zone_id: str,
                 secret: bytes) -> None:
        if puck_type not in PUCK_KINDS:
            raise ValueError(f"unknown puck_type {puck_type}")
        self.devices[device_id] = DeviceRecord(
            device_id=device_id, puck_type=puck_type,
            zone_id=zone_id, secret=secret,
        )

    def ingest(self, raw: dict) -> IngestResult:
        size = len(str(raw).encode())
        if size > MAX_PACKET_BYTES:
            return self._reject("", "oversized_packet")
        try:
            obs = Observation.from_dict(raw)
        except Exception:
            return self._reject("", "invalid_schema")
        if obs.schema_version != 1:
            return self._reject(obs.device_id, "bad_schema_version")
        dev = self.devices.get(obs.device_id)
        if dev is None:
            return self._reject(obs.device_id, "unknown_device")
        if obs.zone_id != dev.zone_id:
            return self._reject(obs.device_id, "zone_mismatch")
        if obs.kind not in PUCK_KINDS[dev.puck_type]:
            return self._reject(obs.device_id, "kind_not_allowed_for_device")
        if not verify(dev.secret, obs):
            return self._reject(obs.device_id, "bad_signature")
        # docs/04: reject stale/replayed sequence — seq must strictly increase
        if obs.seq <= dev.last_seq:
            return self._reject(obs.device_id, "stale_or_replayed_seq")
        dev.last_seq = obs.seq
        now = self.clock()
        dev.last_seen = now
        if obs.kind == EventKind.DEVICE_HEALTH:
            try:
                dev.status = HealthStatus(obs.data.get("status", "ok"))
                dev.last_health_note = str(obs.data.get("note", ""))
            except ValueError:
                dev.status = HealthStatus.DEGRADED
        else:
            dev.status = HealthStatus.OK
        self.accepted.append(obs)
        return IngestResult(True, "ok", obs)

    def refresh_health(self) -> list[Observation]:
        """Mark stale/offline devices and synthesize device_offline events."""
        now = self.clock()
        events = []
        for dev in self.devices.values():
            age = now - dev.last_seen
            if dev.last_seen == 0 or age > self.stale_after_s * 4:
                new = HealthStatus.OFFLINE
            elif age > self.stale_after_s:
                new = HealthStatus.STALE
            else:
                new = HealthStatus.OK if dev.status != HealthStatus.OFFLINE else HealthStatus.STALE
            if new != dev.status:
                dev.status = new
                events.append(Observation(
                    device_id=dev.device_id,
                    seq=0,  # collector-synthesized; not device seq space
                    observed_at=utc_now_iso(),
                    kind=EventKind.DEVICE_OFFLINE,
                    zone_id=dev.zone_id,
                    data={"device_status": new.value, "age_s": round(age, 3),
                          "synthesized_by": "collector"},
                ))
        return events

    def _reject(self, device_id: str, reason: str) -> IngestResult:
        self.rejected.append((device_id, reason))
        return IngestResult(False, reason)
