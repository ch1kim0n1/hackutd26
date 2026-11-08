"""Security posture assessment engine (#126).

Read-only checks over a node/provider interface produce structured
findings: severity, confidence, provenance, evidence refs. Detects
weaknesses BEFORE any attacker event. Fixture-driven until #101 nodes
exist; `unknown` is preserved when evidence is insufficient (never
confirmed without proof, per scope-matrix evidence rules).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Protocol


# ---------------------------------------------------------------------------
# Finding schema
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Confidence(str, Enum):
    UNKNOWN = "unknown"        # insufficient evidence
    SUSPECTED = "suspected"    # weak signal, needs corroboration
    CONFIRMED = "confirmed"    # direct evidence


class Provenance(str, Enum):
    DEMO = "DEMO"              # synthetic fixture
    REPLAY = "REPLAY"          # recorded capture
    LIVE = "LIVE"              # real measurement


@dataclass(frozen=True)
class Finding:
    check_id: str
    node_ref: str
    severity: Severity
    confidence: Confidence
    provenance: Provenance
    summary: str
    evidence_refs: tuple[str, ...] = ()
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "node_ref": self.node_ref,
            "severity": self.severity.value,
            "confidence": self.confidence.value,
            "provenance": self.provenance.value,
            "summary": self.summary,
            "evidence_refs": list(self.evidence_refs),
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Node/provider interface — mirrors #125 node model shape but own schema.
# Swap FixtureProvider for a live provider when #101 lands.
# ---------------------------------------------------------------------------

class NodeView(Protocol):
    """Read-only view of one assessable node."""
    node_id: str
    zone_id: str
    services: tuple[dict, ...]        # {name, port, protocol, version}
    config: dict                      # live config snapshot
    baseline: dict                    # known-good baseline
    open_ports: tuple[dict, ...]      # observed listeners {port, proto}
    patch_level: str                  # e.g. '2026-10' or 'unknown'
    credentials: tuple[dict, ...]     # {user, method, strength}


class Provider(Protocol):
    def nodes(self) -> list[NodeView]: ...
    def provenance(self) -> Provenance: ...


# ---------------------------------------------------------------------------
# Checks — each returns list[Finding]. Deterministic: sorted output.
# ---------------------------------------------------------------------------

def check_open_ports(node: NodeView, prov: Provenance) -> list[Finding]:
    """Flag listeners not in the node's service baseline."""
    out = []
    baseline_ports = {(s["name"], s["port"]) for s in node.services}
    baseline_port_nums = {s["port"] for s in node.services}
    for p in node.open_ports:
        name_match = any(n == p.get("service_name") for n, _ in baseline_ports)
        if p["port"] in baseline_port_nums and name_match:
            continue
        if p["port"] in baseline_port_nums:
            continue  # port expected even if name unknown
        out.append(Finding(
            check_id="open_port_unexpected",
            node_ref=node.node_id,
            severity=Severity.MEDIUM,
            confidence=Confidence.CONFIRMED,
            provenance=prov,
            summary=f"Unexpected listener on port {p['port']}/{p.get('proto','tcp')}",
            evidence_refs=(f"port-scan:{node.node_id}:{p['port']}",),
            detail={"port": p["port"], "proto": p.get("proto", "tcp")},
        ))
    return out


def check_default_credentials(node: NodeView, prov: Provenance) -> list[Finding]:
    """Flag default/weak credential markers."""
    out = []
    for c in node.credentials:
        weak = c.get("strength") in ("default", "weak", "none")
        if weak:
            out.append(Finding(
                check_id="default_credential",
                node_ref=node.node_id,
                severity=Severity.HIGH,
                confidence=Confidence.CONFIRMED,
                provenance=prov,
                summary=f"Weak/default credential for {c.get('user','?')} "
                        f"via {c.get('method','?')}",
                evidence_refs=(f"cred-audit:{node.node_id}:{c.get('user','?')}",),
                detail=dict(c),
            ))
    return out


def check_missing_patch(node: NodeView, prov: Provenance) -> list[Finding]:
    """Flag nodes behind the expected patch level."""
    out = []
    expected = node.baseline.get("expected_patch_level")
    actual = node.patch_level
    if expected and actual and actual != expected:
        # compare as strings; 'unknown' actual -> unknown confidence
        conf = (Confidence.CONFIRMED if actual != "unknown"
                else Confidence.UNKNOWN)
        sev = Severity.HIGH if conf == Confidence.CONFIRMED else Severity.MEDIUM
        out.append(Finding(
            check_id="missing_patch",
            node_ref=node.node_id,
            severity=sev,
            confidence=conf,
            provenance=prov,
            summary=f"Patch level {actual} != expected {expected}",
            evidence_refs=(f"patch:{node.node_id}:{actual}",),
            detail={"expected": expected, "actual": actual},
        ))
    return out


def check_baseline_drift(node: NodeView, prov: Provenance) -> list[Finding]:
    """Diff live config vs baseline; distinguish NEW drift from known."""
    out = []
    known_drift = set(node.baseline.get("accepted_drift", []))
    for key, live_val in node.config.items():
        base_val = node.baseline.get(key)
        if base_val is None or live_val == base_val:
            continue
        is_new = f"{key}={live_val}" not in known_drift and key not in known_drift
        out.append(Finding(
            check_id="baseline_drift_new" if is_new else "baseline_drift_known",
            node_ref=node.node_id,
            severity=Severity.MEDIUM if is_new else Severity.LOW,
            confidence=Confidence.CONFIRMED,
            provenance=prov,
            summary=f"Config drift on {key}: baseline={base_val!r} live={live_val!r}"
                    + (" (new)" if is_new else " (accepted)"),
            evidence_refs=(f"config:{node.node_id}:{key}",),
            detail={"key": key, "baseline": base_val, "live": live_val,
                    "new": is_new},
        ))
    return out


def check_evidence_sufficiency(node: NodeView, prov: Provenance) -> list[Finding]:
    """If a node exposes nothing to assess, emit an UNKNOWN finding —
    never silently pass."""
    if not node.services and not node.config and not node.open_ports:
        return [Finding(
            check_id="insufficient_evidence",
            node_ref=node.node_id,
            severity=Severity.INFO,
            confidence=Confidence.UNKNOWN,
            provenance=prov,
            summary="No assessable surface; posture unknown",
            evidence_refs=(),
        )]
    return []


CHECKS = (
    check_open_ports,
    check_default_credentials,
    check_missing_patch,
    check_baseline_drift,
    check_evidence_sufficiency,
)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class PostureEngine:
    def __init__(self, provider: Provider, checks=CHECKS):
        self.provider = provider
        self.checks = checks

    def assess(self) -> list[dict]:
        """Run all checks over all nodes; deterministic sorted output."""
        prov = self.provider.provenance()
        findings: list[Finding] = []
        for node in sorted(self.provider.nodes(), key=lambda n: n.node_id):
            for check in self.checks:
                findings.extend(check(node, prov))
        # deterministic order: severity desc, then node, then check
        order = {s: i for i, s in enumerate(
            [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM,
             Severity.LOW, Severity.INFO])}
        findings.sort(key=lambda f: (order[f.severity], f.node_ref,
                                     f.check_id, f.summary))
        return [f.as_dict() for f in findings]


# ---------------------------------------------------------------------------
# Fixture provider + seeded weakness for tests/demo
# ---------------------------------------------------------------------------

@dataclass
class FixtureNode:
    node_id: str
    zone_id: str = "rack-01"
    services: tuple = ()
    config: dict = field(default_factory=dict)
    baseline: dict = field(default_factory=dict)
    open_ports: tuple = ()
    patch_level: str = "unknown"
    credentials: tuple = ()


class FixtureProvider:
    """In-memory provider; swap for live node services in #101/#102."""

    def __init__(self, nodes: list[FixtureNode], provenance=Provenance.DEMO):
        self._nodes = nodes
        self._prov = provenance

    def nodes(self):
        return list(self._nodes)

    def provenance(self):
        return self._prov


def seed_weak_fixture() -> FixtureProvider:
    """One node with planted weaknesses; used by tests + demo."""
    return FixtureProvider([
        FixtureNode(
            node_id="vpi-compute-01",
            zone_id="rack-01",
            services=({"name": "sshd", "port": 22, "protocol": "tcp",
                       "version": "OpenSSH_9.6"},),
            config={"ssh_password_auth": True, "auto_updates": True},
            baseline={"ssh_password_auth": False, "auto_updates": True,
                      "expected_patch_level": "2026-10",
                      "accepted_drift": []},
            open_ports=({"port": 22, "proto": "tcp", "service_name": "sshd"},
                        {"port": 23, "proto": "tcp", "service_name": "telnet"},
                        {"port": 8080, "proto": "tcp"}),
            patch_level="2026-08",
            credentials=({"user": "pi", "method": "ssh-password",
                          "strength": "default"},),
        ),
        FixtureNode(
            node_id="vpi-network-01",
            zone_id="lab-b",
            services=({"name": "snmpd", "port": 161, "protocol": "udp"},),
            config={"snmp_community_write": False},
            baseline={"snmp_community_write": False,
                      "expected_patch_level": "2026-10"},
            open_ports=({"port": 161, "proto": "udp",
                         "service_name": "snmpd"},),
            patch_level="2026-10",
            credentials=({"user": "snmp", "method": "community",
                          "strength": "strong"},),
        ),
    ])
