"""Canonical observation event model (docs/04-DATA-AND-INTERFACES.md)."""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

SCHEMA_VERSION = 1
MAX_PACKET_BYTES = 4096


class EventKind(str, Enum):
    WIFI_AP_SEEN = "wifi_ap_seen"
    CABINET_CONTACT_OPEN = "cabinet_contact_open"
    CABINET_CONTACT_CLOSED = "cabinet_contact_closed"
    BLE_BEACON_SEEN = "ble_beacon_seen"
    DEVICE_HEALTH = "device_health"
    # collector-synthesized, never emitted by a puck
    DEVICE_OFFLINE = "device_offline"


PUCK_KINDS: dict[str, frozenset[EventKind]] = {
    "puck-a": frozenset({EventKind.WIFI_AP_SEEN, EventKind.DEVICE_HEALTH}),
    "puck-b": frozenset({
        EventKind.CABINET_CONTACT_OPEN,
        EventKind.CABINET_CONTACT_CLOSED,
        EventKind.DEVICE_HEALTH,
    }),
    "puck-c": frozenset({EventKind.BLE_BEACON_SEEN, EventKind.DEVICE_HEALTH}),
}


class HealthStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    STALE = "stale"


@dataclass
class Observation:
    """One canonical event payload exactly per docs/04."""

    device_id: str
    seq: int
    observed_at: str
    kind: EventKind
    zone_id: str
    data: dict[str, Any]
    event_id: str = field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    schema_version: int = SCHEMA_VERSION
    signature: str = ""

    def canonical(self) -> bytes:
        payload = {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "device_id": self.device_id,
            "seq": self.seq,
            "observed_at": self.observed_at,
            "kind": self.kind.value,
            "zone_id": self.zone_id,
            "data": self.data,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    def to_dict(self) -> dict[str, Any]:
        d = {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "device_id": self.device_id,
            "seq": self.seq,
            "observed_at": self.observed_at,
            "kind": self.kind.value,
            "zone_id": self.zone_id,
            "data": self.data,
        }
        if self.signature:
            d["signature"] = self.signature
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Observation":
        return cls(
            device_id=str(raw["device_id"]),
            seq=int(raw["seq"]),
            observed_at=str(raw["observed_at"]),
            kind=EventKind(raw["kind"]),
            zone_id=str(raw["zone_id"]),
            data=dict(raw.get("data", {})),
            event_id=str(raw.get("event_id", "")),
            schema_version=int(raw.get("schema_version", 0)),
            signature=str(raw.get("signature", "")),
        )


def utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
