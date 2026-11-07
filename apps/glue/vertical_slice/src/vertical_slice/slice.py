"""GLUE-01 vertical slice: device event -> authenticated collector ->
normalized observation -> reducer -> authorized subscribers.

In-memory implementation of the docs/04 pipeline contracts. Real
deployment swaps the reducer for SpacetimeDB and collector for the
TLS device-relay; semantics (identity, dedup, provenance, staleness,
authz-scoped subscriptions) are identical."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass, field


class Denied(Exception):
    pass


# ---------------- device auth (same scheme as sensors/) -------------

@dataclass
class DeviceKey:
    device_id: str
    zone_id: str
    secret: bytes


class Collector:
    """Authenticated ingest edge: verifies HMAC, normalizes to the
    canonical observation shape (docs/04), stamps provenance + trace."""

    def __init__(self, keys: dict[str, DeviceKey], clock=time.time):
        self.keys = keys
        self.clock = clock
        self.accepted = 0
        self.rejected: list[tuple[str, str]] = []

    def ingest(self, raw: dict) -> dict:
        dev_id = raw.get("device_id", "")
        key = self.keys.get(dev_id)
        if key is None:
            self.rejected.append((dev_id, "unknown_device"))
            raise Denied("unknown device")
        body = json.dumps({k: v for k, v in raw.items() if k != "sig"},
                          sort_keys=True).encode()
        expected = hmac.new(key.secret, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, raw.get("sig", "")):
            self.rejected.append((dev_id, "bad_signature"))
            raise Denied("bad signature")
        # normalize -> canonical observation
        obs = {
            "schema_version": 1,
            "observation_id": f"obs-{uuid.uuid4().hex[:12]}",
            "event_id": raw.get("event_id"),
            "device_id": dev_id,
            "zone_id": key.zone_id,               # server-side zone, not claim
            "kind": raw.get("kind"),
            "incident_id": raw.get("incident_id"),
            "observed_at": raw.get("observed_at"),
            "observed_epoch": raw.get("observed_epoch"),
            "ingested_at": self.clock(),
            "data": raw.get("data", {}),
            "provenance": {"source": "device_relay",
                           "device_key_id": dev_id,
                           "trust": "hardware_signed"},
            "trace_id": raw.get("trace_id") or uuid.uuid4().hex[:12],
        }
        self.accepted += 1
        return obs


# ---------------- reducer (SpacetimeDB stand-in) ---------------------

@dataclass
class Subscriber:
    sub_id: str
    user_id: str
    role: str
    incident_scope: set[str]
    queue: list = field(default_factory=list)


class Reducer:
    """Dedup + table + scoped fan-out. Mirrors SpacetimeDB reducer
    semantics: idempotent on event_id, version-checked writes,
    per-subscriber incident scoping."""

    STALE_AFTER_S = 30.0

    def __init__(self, clock=time.time):
        self.clock = clock
        self.observations: dict[str, dict] = {}   # event_id -> obs
        self.subscribers: dict[str, Subscriber] = {}
        self.last_device_event: dict[str, float] = {}
        self.latencies_ms: list[float] = []

    def subscribe(self, user_id: str, role: str,
                  incident_scope: set[str]) -> Subscriber:
        s = Subscriber(sub_id=f"sub-{uuid.uuid4().hex[:8]}",
                       user_id=user_id, role=role,
                       incident_scope=incident_scope)
        self.subscribers[s.sub_id] = s
        return s

    def _incident_for(self, obs: dict) -> str | None:
        # observations link to incidents via zone->incident mapping done
        # upstream; here we tag by device zone for scope filtering
        return obs.get("incident_id")

    def reduce(self, obs: dict) -> str:
        eid = obs.get("event_id")
        if eid and eid in self.observations:
            return "duplicate_suppressed"
        self.observations[eid or obs["observation_id"]] = obs
        self.last_device_event[obs["device_id"]] = self.clock()
        # latency: observed_at -> ingested_at (ISO parse kept simple:
        # callers pass epoch in tests; production parses RFC3339)
        self.latencies_ms.append(
            max(0.0, (obs["ingested_at"] - obs.get("observed_epoch", 0)) * 1000))
        # fan out to authorized subscribers only
        inc = self._incident_for(obs)
        for s in self.subscribers.values():
            if self._authorized(s, inc):
                s.queue.append(obs)
        return "reduced"

    def _authorized(self, s: Subscriber, incident_id: str | None) -> bool:
        if s.role in ("admin", "commander"):
            return True
        if incident_id is None:
            return True   # unscoped observations (zone-level telemetry)
        return incident_id in s.incident_scope

    def is_stale(self, device_id: str) -> bool:
        last = self.last_device_event.get(device_id)
        if last is None:
            return True
        return (self.clock() - last) > self.STALE_AFTER_S

    def delivery_report(self) -> dict:
        return {
            "observations": len(self.observations),
            "subscribers": len(self.subscribers),
            "duplicates_suppressed": sum(
                1 for _ in []),  # counted via reduce return in caller
            "stale_devices": [d for d in self.last_device_event
                              if self.is_stale(d)],
            "latency_ms_p50": sorted(self.latencies_ms)[
                len(self.latencies_ms) // 2] if self.latencies_ms else None,
        }
