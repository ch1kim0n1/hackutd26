"""Virtual Pi node model for the data-center simulator (#125).

Node = identity + role + services + addresses + heartbeat + config
baseline + health model. Pure data + deterministic transitions; no
transport, no I/O.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

SCHEMA_VERSION = 1
TICK_MS = 1000  # one simulated second per tick


class NodeRole(str, Enum):
    COMPUTE = "compute"        # hypervisor / workload host
    NETWORK = "network"        # switch/router control plane
    SENSOR = "sensor"          # environmental/contact/RF puck
    MANAGEMENT = "management"  # OOB/iDRAC/bmc-style node


class HealthState(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    FAULT = "fault"
    STALE = "stale"            # heartbeat missed; inferred, not asserted


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    port: int
    protocol: str = "tcp"      # tcp | udp
    version: str = ""
    required: bool = True


@dataclass(frozen=True)
class NodeProfile:
    """Static identity/config for a virtual Pi node."""
    node_id: str
    role: NodeRole
    hostname: str
    zone_id: str
    addresses: tuple[str, ...]        # ip:port or mac-like labels
    services: tuple[ServiceSpec, ...]
    config_baseline: dict             # hashed + diffable
    heartbeat_interval_ticks: int = 5
    stale_after_ticks: int = 15

    @property
    def baseline_hash(self) -> str:
        blob = json.dumps(self.config_baseline, sort_keys=True,
                          separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# The four canonical virtual Pi profiles for PHX-1 (Meridian Datacenters).
# ---------------------------------------------------------------------------

PI_PROFILES: tuple[NodeProfile, ...] = (
    NodeProfile(
        node_id="vpi-compute-01",
        role=NodeRole.COMPUTE,
        hostname="vpi-compute-01.phx1.meridian",
        zone_id="rack-01",
        addresses=("192.0.2.101", "02:de:00:00:00:01"),
        services=(
            ServiceSpec("sshd", 22, version="OpenSSH_9.6"),
            ServiceSpec("hypervisor-agent", 443, version="hv-agent/2.4.1"),
            ServiceSpec("metrics", 9100, version="node-exporter/1.8"),
        ),
        config_baseline={
            "os": "raspios-64-2026-09",
            "kernel": "6.6.31-rt",
            "ssh_password_auth": False,
            "auto_updates": True,
            "fw_profile": "restricted-egress",
        },
    ),
    NodeProfile(
        node_id="vpi-network-01",
        role=NodeRole.NETWORK,
        hostname="vpi-network-01.phx1.meridian",
        zone_id="lab-b",
        addresses=("192.0.2.102", "02:de:00:00:00:02"),
        services=(
            ServiceSpec("snmpd", 161, "udp", version="net-snmp/5.9.4"),
            ServiceSpec("netconf", 830, version="libnetconf2/2.4"),
            ServiceSpec("lldp", 116, "udp"),
        ),
        config_baseline={
            "os": "raspios-64-2026-09",
            "snmp_community_write": False,
            "lldp_tx": True,
            "fw_profile": "restricted-egress",
        },
    ),
    NodeProfile(
        node_id="vpi-sensor-01",
        role=NodeRole.SENSOR,
        hostname="vpi-sensor-01.phx1.meridian",
        zone_id="rack-01",
        addresses=("192.0.2.103", "02:de:00:00:00:03"),
        services=(
            ServiceSpec("mqtt-edge", 1883, version="paho/1.6"),
            ServiceSpec("contact-daemon", 0, protocol="internal"),
        ),
        config_baseline={
            "os": "raspios-64-2026-09",
            "mqtt_tls": True,
            "ble_scan": True,
            "fw_profile": "restricted-egress",
        },
    ),
    NodeProfile(
        node_id="vpi-mgmt-01",
        role=NodeRole.MANAGEMENT,
        hostname="vpi-mgmt-01.phx1.meridian",
        zone_id="bench-row",
        addresses=("192.0.2.104", "02:de:00:00:00:04"),
        services=(
            ServiceSpec("sshd", 22, version="OpenSSH_9.6"),
            ServiceSpec("idrac-lite", 443, version="mgmt/1.2"),
            ServiceSpec("jump-host", 2222, version="openssh/9.6"),
        ),
        config_baseline={
            "os": "raspios-64-2026-09",
            "ssh_password_auth": False,
            "mfa_required": True,
            "jump_acl": ["ops-net", "lab-net"],
            "fw_profile": "restricted-egress",
        },
    ),
)


@dataclass
class SimNode:
    """Runtime state for one simulated node."""
    profile: NodeProfile
    health: HealthState = HealthState.OK
    killed: bool = False
    hung: bool = False               # alive but silent (watchdog target)
    tick: int = 0
    seq: int = 0                      # per-node observation sequence
    last_heartbeat_tick: int = 0
    missed_heartbeats: int = 0
    uptime_ticks: int = 0
    drift: dict = field(default_factory=dict)  # live config vs baseline
    # Observed listeners beyond the declared service baseline. Injected by
    # failure scenarios; reported via `service_inventory` observations.
    extra_listeners: list = field(default_factory=list)
    # Optional sustained CPU override (percent) for load scenarios; None =
    # seeded jitter. Reported via `resource_metric` observations.
    cpu_pct_override: Optional[float] = None

    @property
    def node_id(self) -> str:
        return self.profile.node_id

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq
