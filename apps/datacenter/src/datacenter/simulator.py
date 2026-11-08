"""Deterministic data-center simulator (#125 core).

Logical clock in ticks (1 tick = 1 s). Every node heartbeats on its own
interval; missed heartbeats degrade then mark the node STALE (staleness
is inferred from silence, never asserted by the node itself). kill() /
revive() give failure-injection isolation: one node's death does not
affect the others.

Emitted observations are canonical-envelope dicts per
docs/13-INTEGRATION-CONTRACTS.md section 1. This package does NOT
transport them; #100 wires publish later.
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from .nodes import (
    HealthState, NodeProfile, PI_PROFILES, SCHEMA_VERSION, SimNode, TICK_MS,
)

EPOCH = datetime(2026, 11, 7, 18, 0, 0, tzinfo=timezone.utc)


def tick_to_iso(tick: int) -> str:
    """Deterministic logical timestamp for a tick (no wall clock)."""
    return (EPOCH + timedelta(milliseconds=tick * TICK_MS)).strftime(
        "%Y-%m-%dT%H:%M:%S.") + f"{(tick * TICK_MS) % 1000:03d}Z"


def make_event_id(node_id: str, seq: int, tick: int) -> str:
    blob = f"{node_id}:{seq}:{tick}".encode()
    return "evt-" + hashlib.sha256(blob).hexdigest()[:16]


def canonical_observation(node: SimNode, tick: int, kind: str,
                          data: dict) -> dict:
    """Build a contract-shaped observation dict (not yet published)."""
    seq = node.next_seq()
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": make_event_id(node.node_id, seq, tick),
        "device_id": node.node_id,
        "seq": seq,
        "observed_at": tick_to_iso(tick),
        "kind": kind,
        "zone_id": node.profile.zone_id,
        "data": data,
    }


class DataCenterSim:
    """Deterministic simulator over the four virtual Pi nodes."""

    def __init__(self, seed: int = 7, profiles=None):
        self.seed = seed
        self._rng = random.Random(seed)
        profiles = profiles or PI_PROFILES
        self.nodes: dict[str, SimNode] = {
            p.node_id: SimNode(profile=p) for p in profiles
        }
        self.tick_count = 0
        self._outbox: list[dict] = []

    # -- lifecycle ---------------------------------------------------------

    def reset(self) -> None:
        """Deterministic reset: identical state to a fresh sim with seed."""
        self.__init__(self.seed)

    # -- failure injection --------------------------------------------------

    def kill(self, node_id: str) -> None:
        n = self.nodes[node_id]
        n.killed = True
        n.health = HealthState.FAULT
        self._emit(n, "device_health",
                   {"status": "fault", "note": "simulated power loss",
                    "firmware": "vpi-sim-0.1"})

    def revive(self, node_id: str) -> None:
        n = self.nodes[node_id]
        n.killed = False
        n.health = HealthState.OK
        n.missed_heartbeats = 0
        n.last_heartbeat_tick = self.tick_count
        self._emit(n, "device_health",
                   {"status": "ok", "note": "recovered", "firmware": "vpi-sim-0.1"})

    def inject_drift(self, node_id: str, key: str, value) -> None:
        """Mutate live config away from baseline (posture check input)."""
        n = self.nodes[node_id]
        n.drift[key] = value
        if n.profile.config_baseline.get(key) != value:
            self._emit(n, "device_health",
                       {"status": "degraded", "note": f"config drift: {key}",
                        "firmware": "vpi-sim-0.1"})

    # -- clock ---------------------------------------------------------------

    def tick(self) -> list[dict]:
        """Advance one tick; returns observations emitted this tick."""
        self.tick_count += 1
        emitted: list[dict] = []
        for node in self.nodes.values():
            emitted.extend(self._node_tick(node))
        # outbox mirrors what a transport would drain
        self._outbox.extend(emitted)
        return emitted

    def drain(self) -> list[dict]:
        out, self._outbox = self._outbox, []
        return out

    # -- internals -----------------------------------------------------------

    def _node_tick(self, node: SimNode) -> list[dict]:
        out: list[dict] = []
        node.tick = self.tick_count
        node.uptime_ticks += 1

        if node.killed or node.hung:
            # dead/hung nodes emit nothing; silence drives STALE below
            pass
        else:
            due = (self.tick_count - node.last_heartbeat_tick
                   >= node.profile.heartbeat_interval_ticks)
            if due:
                node.last_heartbeat_tick = self.tick_count
                node.missed_heartbeats = 0
                node.health = (HealthState.DEGRADED
                               if node.drift else HealthState.OK)
                out.append(self._emit(node, "device_health", {
                    "status": node.health.value,
                    "note": "heartbeat",
                    "firmware": "vpi-sim-0.1",
                    "uptime_s": node.uptime_ticks,
                    "services": len(node.profile.services),
                }))
            # deterministic jitter: occasionally emit a sensor-ish metric
            if self._rng.random() < 0.05:
                out.append(self._emit(node, "temperature", {
                    "celsius": round(24.0 + self._rng.uniform(-2, 8), 1),
                    "sensor": "soc-thermal",
                }))

        # staleness: missed heartbeats mark node stale (inferred)
        missed = (self.tick_count - node.last_heartbeat_tick
                  >= node.profile.stale_after_ticks)
        if missed and not node.killed and node.health != HealthState.STALE:
            node.health = HealthState.STALE
            out.append(self._emit(node, "device_health", {
                "status": "stale",
                "note": "heartbeat missed",
                "firmware": "vpi-sim-0.1",
            }))
        return out

    def _emit(self, node: SimNode, kind: str, data: dict) -> dict:
        obs = canonical_observation(node, self.tick_count, kind, data)
        return obs
