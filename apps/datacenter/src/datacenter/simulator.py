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

# Periodic self-report cadences (ticks = simulated seconds).
METRIC_INTERVAL_TICKS = 10     # resource_metric per live node
INVENTORY_INTERVAL_TICKS = 30  # service_inventory per live node
FLOW_BACKGROUND_P = 0.03       # per-tick chance of a benign flow record


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
        # Observations emitted between ticks (failure injection, on-demand
        # flows) queue here and are flushed by the next tick()/drain() —
        # nothing the sim "says" is silently dropped.
        self._pending: list[dict] = []

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
        n.hung = False
        n.health = HealthState.OK
        n.missed_heartbeats = 0
        n.last_heartbeat_tick = self.tick_count
        self._emit(n, "device_health",
                   {"status": "ok", "note": "recovered",
                    "recovered": True, "firmware": "vpi-sim-0.1"})

    def inject_drift(self, node_id: str, key: str, value) -> None:
        """Mutate live config away from baseline (posture check input)."""
        n = self.nodes[node_id]
        n.drift[key] = value
        if n.profile.config_baseline.get(key) != value:
            self._emit(n, "device_health",
                       {"status": "degraded", "note": f"config drift: {key}",
                        "firmware": "vpi-sim-0.1"})
            self._emit(n, "config_drift",
                       {"key": key,
                        "baseline": n.profile.config_baseline.get(key),
                        "live": value,
                        "resolved": False})

    def heal_drift(self, node_id: str, key: str) -> None:
        """Restore a drifted key to baseline; emits recovery signal."""
        n = self.nodes[node_id]
        if key not in n.drift:
            return
        baseline = n.profile.config_baseline.get(key)
        n.drift.pop(key, None)
        self._emit(n, "config_drift",
                   {"key": key, "baseline": baseline,
                    "live": baseline, "resolved": True})
        if not n.drift and not n.killed:
            n.health = HealthState.OK
            self._emit(n, "device_health",
                       {"status": "ok", "note": "recovered",
                        "recovered": True, "firmware": "vpi-sim-0.1"})

    # -- scenario primitives -------------------------------------------------

    def inject_service(self, node_id: str, name: str, port: int,
                       proto: str = "tcp", version: str = "") -> None:
        """Add an unexpected listener; emits service_inventory immediately."""
        n = self.nodes[node_id]
        listener = {"name": name, "port": port, "proto": proto,
                    "version": version}
        if listener not in n.extra_listeners:
            n.extra_listeners.append(listener)
        self._emit_inventory(n)

    def heal_service(self, node_id: str, port: int) -> None:
        """Remove an injected listener; emits clean inventory."""
        n = self.nodes[node_id]
        n.extra_listeners = [l for l in n.extra_listeners
                             if l["port"] != port]
        self._emit_inventory(n)

    def set_load(self, node_id: str, cpu_pct: float) -> None:
        """Sustain a CPU level (benign-load scenario input)."""
        self.nodes[node_id].cpu_pct_override = cpu_pct

    def clear_load(self, node_id: str) -> None:
        self.nodes[node_id].cpu_pct_override = None

    def emit_flow(self, node_id: str, **fields) -> dict:
        """Emit one objective network_flow record (NetFlow-style facts —
        no verdict/label fields; classification is the correlator's job)."""
        n = self.nodes[node_id]
        data = {"src": fields.get("src", ""), "dst": fields.get("dst", ""),
                "proto": fields.get("proto", "tcp"),
                "packets": int(fields.get("packets", 0)),
                "bytes": int(fields.get("bytes", 0)),
                "duration_s": float(fields.get("duration_s", 0.0))}
        for opt in ("dst_port", "distinct_dst_ports", "direction", "flags"):
            if fields.get(opt) is not None:
                data[opt] = fields[opt]
        return self._emit(n, "network_flow", data)

    # -- clock ---------------------------------------------------------------

    def tick(self) -> list[dict]:
        """Advance one tick; returns observations emitted this tick
        (including any queued by injections since the last tick)."""
        self.tick_count += 1
        for node in self.nodes.values():
            self._node_tick(node)
        emitted, self._pending = self._pending, []
        # outbox mirrors what a transport would drain
        self._outbox.extend(emitted)
        return emitted

    def drain(self) -> list[dict]:
        if self._pending:
            self._outbox.extend(self._pending)
            self._pending = []
        out, self._outbox = self._outbox, []
        return out

    # -- internals -----------------------------------------------------------

    def _node_tick(self, node: SimNode) -> None:
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
                self._emit(node, "device_health", {
                    "status": node.health.value,
                    "note": "heartbeat",
                    "firmware": "vpi-sim-0.1",
                    "uptime_s": node.uptime_ticks,
                    "services": len(node.profile.services),
                })
            if self.tick_count % METRIC_INTERVAL_TICKS == 0:
                self._emit_metric(node)
            if self.tick_count % INVENTORY_INTERVAL_TICKS == 0:
                self._emit_inventory(node)
            # deterministic jitter: occasionally emit sensor-ish metrics
            # and a benign background flow record
            if self._rng.random() < 0.05:
                self._emit(node, "temperature", {
                    "celsius": round(24.0 + self._rng.uniform(-2, 8), 1),
                    "sensor": "soc-thermal",
                })
            if self._rng.random() < FLOW_BACKGROUND_P:
                self._emit_background_flow(node)

        # staleness: missed heartbeats mark node stale (inferred)
        missed = (self.tick_count - node.last_heartbeat_tick
                  >= node.profile.stale_after_ticks)
        if missed and not node.killed and node.health != HealthState.STALE:
            node.health = HealthState.STALE
            self._emit(node, "device_health", {
                "status": "stale",
                "note": "heartbeat missed",
                "firmware": "vpi-sim-0.1",
            })

    def _emit_metric(self, node: SimNode) -> None:
        """Periodic resource_metric self-report (objective counters only —
        high CPU alone is NOT an anomaly; the correlator decides)."""
        cpu = (node.cpu_pct_override if node.cpu_pct_override is not None
               else round(self._rng.uniform(3, 45), 1))
        self._emit(node, "resource_metric", {
            "cpu_pct": cpu,
            "mem_pct": round(self._rng.uniform(10, 70), 1),
            "load1": round(self._rng.uniform(0.01, 1.2), 2),
            "interval_s": METRIC_INTERVAL_TICKS,
        })

    def _emit_inventory(self, node: SimNode) -> None:
        """Listener inventory: declared services + observed extras, with
        the extras flagged `unexpected` (self-report vs own baseline)."""
        listeners = [
            {"name": s.name, "port": s.port, "proto": s.protocol,
             "version": s.version, "expected": True}
            for s in node.profile.services
        ]
        unexpected = [
            {"name": l["name"], "port": l["port"], "proto": l["proto"]}
            for l in node.extra_listeners
        ]
        listeners.extend({**l, "expected": False}
                         for l in node.extra_listeners)
        self._emit(node, "service_inventory", {
            "listeners": listeners,
            "unexpected": unexpected,
        })

    def _emit_background_flow(self, node: SimNode) -> None:
        """Benign lab traffic: metrics scrape / mqtt keepalive shape."""
        ip = node.profile.addresses[0]
        peers = ["192.0.2.10", "192.0.2.20", "192.0.2.30"]
        peer = self._rng.choice(peers)
        port = self._rng.choice([9100, 1883, 443])
        self._emit(node, "network_flow", {
            "src": peer, "dst": ip, "proto": "tcp", "dst_port": port,
            "packets": self._rng.randint(2, 40),
            "bytes": self._rng.randint(200, 8000),
            "duration_s": round(self._rng.uniform(0.05, 2.0), 3),
            "direction": "ingress",
        })

    def _emit(self, node: SimNode, kind: str, data: dict) -> dict:
        obs = canonical_observation(node, self.tick_count, kind, data)
        self._pending.append(obs)
        return obs
