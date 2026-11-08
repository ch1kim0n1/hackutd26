"""Registered-device network inspection targets + structured evidence.

``inspect_zone`` missions resolve their checkpoint (``zone_id`` +
``waypoint_id`` — both already whitelisted by ``mission_contract.py``) to a
*registered* Raspberry Pi target from ``config/inspection_targets.json``.
At the checkpoint the rover runs bounded, allowlisted network health checks
(``netinspect.py``) plus simulated wireless observations, then stores a
structured report next to the camera evidence.

Evidence discipline matches ``camera.py``/ADR-008: the report JSON artifact
carries full detail on disk; downstream consumers get a reference +
SHA-256 + common ``sentinel.rover.evidence`` mapping. Simulated adapters
mark ``synthetic: true`` / ``provenance: DEMO`` — sim evidence is never
presented as LIVE (docs/13).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional

SCHEMA_VERSION = 1
REPORT_KIND = "network_inspection"

# Allowlisted health-check vocabulary. Anything else is rejected at config
# load AND again inside the live adapter — the allowlist is the boundary.
CHECK_TYPES = frozenset({"ping", "tcp_connect", "http_health"})
MAX_CHECKS_PER_TARGET = 8
DEFAULT_CHECKS = (
    {"type": "ping"},
    {"type": "tcp_connect", "port": 22},
)

# Report status vocabulary (closed set — downstream switches on this).
STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_UNREACHABLE = "unreachable"
STATUS_ERROR = "error"
STATUS_STALE = "stale"
STATUS_NO_TARGET = "no_registered_target"
STATUS_DENIED = "denied"
REPORT_STATUSES = frozenset({
    STATUS_OK, STATUS_DEGRADED, STATUS_UNREACHABLE, STATUS_ERROR,
    STATUS_STALE, STATUS_NO_TARGET, STATUS_DENIED,
})


def _is_str(v) -> bool:
    return isinstance(v, str) and len(v) > 0


def check_name(spec: Mapping) -> str:
    """Stable identifier for a check spec, e.g. ``tcp_connect:22``."""
    t = spec.get("type", "")
    if t == "http_health":
        return f"http_health:{spec.get('port')}" + str(spec.get("path", "/healthz"))
    if t in ("tcp_connect",):
        return f"tcp_connect:{spec.get('port')}"
    return str(t)


def validate_check_spec(spec) -> tuple[bool, str]:
    """Allowlist + bounds for one health-check spec. (ok, reason)."""
    if not isinstance(spec, Mapping):
        return False, "check_not_object"
    t = spec.get("type")
    if t not in CHECK_TYPES:
        return False, f"check_type_not_allowlisted:{t}"
    if t in ("tcp_connect", "http_health"):
        port = spec.get("port")
        if not isinstance(port, int) or isinstance(port, bool) \
                or not (1 <= port <= 65535):
            return False, "bad_port"
    if t == "http_health":
        path = spec.get("path", "/healthz")
        if not isinstance(path, str) or not path.startswith("/") \
                or " " in path or ".." in path:
            return False, "bad_path"
    return True, ""


@dataclass(frozen=True)
class InspectionTarget:
    """One registered Raspberry Pi inspection checkpoint.

    ``zone_id`` + ``waypoint_id`` bind the target to a surveyed checkpoint
    (the same whitelist inspect_zone missions already validate against);
    ``address`` is the allowlisted network address health checks may use.
    """

    device_id: str          # the Pi being inspected (e.g. "pi-rack-01")
    zone_id: str
    waypoint_id: str
    address: str            # IP/hostname — allowlisted for live checks
    ssid: str = ""          # expected wireless identity (sim observations)
    bssid: str = ""         # expected BSSID (sim observations)
    label: str = ""
    cabinet_id: str = ""    # physical cabinet this Pi serves (hw adapter)
    checks: tuple = ()      # tuple of validated check spec dicts

    @classmethod
    def from_dict(cls, data: Mapping) -> "InspectionTarget":
        if not isinstance(data, Mapping):
            raise ValueError("inspection target is not an object")
        for f in ("device_id", "zone_id", "waypoint_id", "address"):
            if not _is_str(data.get(f)):
                raise ValueError(f"inspection target missing {f}")
        raw_checks = data.get("checks")
        if raw_checks is None:
            specs = [dict(c) for c in DEFAULT_CHECKS]
        elif isinstance(raw_checks, list):
            specs = [dict(c) for c in raw_checks]
        else:
            raise ValueError("checks must be a list")
        if not specs:
            raise ValueError("checks must not be empty")
        if len(specs) > MAX_CHECKS_PER_TARGET:
            raise ValueError(f"too many checks (max {MAX_CHECKS_PER_TARGET})")
        for spec in specs:
            ok, reason = validate_check_spec(spec)
            if not ok:
                raise ValueError(f"invalid check spec: {reason}")
        # dedupe identical checks
        seen = set()
        uniq = []
        for s in specs:
            key = json.dumps(s, sort_keys=True)
            if key not in seen:
                seen.add(key)
                uniq.append(s)
        return cls(
            device_id=data["device_id"], zone_id=data["zone_id"],
            waypoint_id=data["waypoint_id"], address=data["address"],
            ssid=str(data.get("ssid", "")), bssid=str(data.get("bssid", "")),
            label=str(data.get("label", "")),
            cabinet_id=str(data.get("cabinet_id", "")),
            checks=tuple(uniq),
        )


class InspectionRegistry:
    """Waypoint -> registered Pi lookup. Empty registry = inspections run
    but report ``no_registered_target`` (honest, never guessed)."""

    def __init__(self, targets=(), device_id: str = ""):
        self.device_id = device_id
        self._by_checkpoint = {}
        self._by_device = {}
        for t in targets:
            self._by_checkpoint[(t.zone_id, t.waypoint_id)] = t
            self._by_device[t.device_id] = t

    @classmethod
    def from_dict(cls, data: Mapping) -> "InspectionRegistry":
        if not isinstance(data, Mapping):
            raise ValueError("inspection targets config is not an object")
        targets = []
        seen_wp = set()
        seen_dev = set()
        for raw in data.get("targets", []):
            t = InspectionTarget.from_dict(raw)
            key = (t.zone_id, t.waypoint_id)
            if key in seen_wp:
                raise ValueError(f"duplicate inspection target {key}")
            if t.device_id in seen_dev:
                raise ValueError(f"duplicate inspection device {t.device_id}")
            seen_wp.add(key)
            seen_dev.add(t.device_id)
            targets.append(t)
        return cls(targets, device_id=str(data.get("device_id", "")))

    @classmethod
    def load(cls, path) -> "InspectionRegistry":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def target_for(self, zone_id: str, waypoint_id: str) -> Optional[InspectionTarget]:
        return self._by_checkpoint.get((zone_id, waypoint_id))

    def target(self, device_id: str) -> Optional[InspectionTarget]:
        return self._by_device.get(device_id)

    def addresses(self) -> frozenset:
        """Allowlisted addresses — the live adapter may ONLY touch these."""
        return frozenset(t.address for t in self._by_device.values())

    def cabinet_ids(self) -> frozenset:
        """Registered cabinet_ids — the hardware adapter's allowlist."""
        return frozenset(t.cabinet_id for t in self._by_device.values()
                         if t.cabinet_id)

    def __len__(self) -> int:
        return len(self._by_device)


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


@dataclass
class InspectionReport:
    """Structured inspection outcome — the evidence artifact body.

    Contains everything requirement: incident/mission/device ids, UTC
    timestamps, per-check results, wireless observations, provenance and
    adapter identity. ``synthetic`` mirrors the camera-evidence convention:
    simulated adapters are honestly labeled, never passed off as real.
    """

    report_id: str
    incident_id: str
    mission_id: str
    command_id: str
    device_id: str            # observing rover
    target_device_id: str     # inspected Pi ("" when no target registered)
    cabinet_id: str           # physical cabinet addressed via hw adapter
    zone_id: str
    waypoint_id: str
    pose: dict
    started_epoch: float
    completed_epoch: float
    status: str
    status_detail: str = ""
    adapter: str = ""         # "simulated" | "live" | "none"
    provenance: str = "DEMO"  # DEMO | REPLAY | LIVE (docs/13 vocabulary)
    synthetic: bool = True
    checks: list = field(default_factory=list)
    observations: list = field(default_factory=list)
    evidence_refs: list = field(default_factory=list)  # refs reported by the inspector

    @property
    def started_at(self) -> str:
        return _iso(self.started_epoch)

    @property
    def completed_at(self) -> str:
        return _iso(self.completed_epoch)

    @property
    def duration_ms(self) -> int:
        return int(max(0.0, (self.completed_epoch - self.started_epoch) * 1000))

    def is_stale(self, now: float, max_age_s: float) -> bool:
        """Result finalized longer ago than ``max_age_s`` is stale."""
        return max_age_s > 0 and (now - self.completed_epoch) > max_age_s

    def summary(self) -> dict:
        ok = sum(1 for c in self.checks if c.get("ok"))
        return {
            "status": self.status,
            "target_device_id": self.target_device_id,
            "checks_ok": ok,
            "checks_failed": len(self.checks) - ok,
            "observations": len(self.observations),
            "duration_ms": self.duration_ms,
        }

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "kind": REPORT_KIND,
            "report_id": self.report_id,
            "incident_id": self.incident_id,
            "mission_id": self.mission_id,
            "command_id": self.command_id,
            "device_id": self.device_id,
            "target_device_id": self.target_device_id,
            "cabinet_id": self.cabinet_id,
            "zone_id": self.zone_id,
            "waypoint_id": self.waypoint_id,
            "pose": self.pose,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "status_detail": self.status_detail,
            "adapter": self.adapter,
            "provenance": self.provenance,
            "synthetic": self.synthetic,
            "summary": self.summary(),
            "checks": self.checks,
            "observations": self.observations,
            "evidence_refs": self.evidence_refs,
        }


def new_report(ctx: Mapping, **fields) -> InspectionReport:
    """Build an InspectionReport from a mission/inspection context mapping.

    ``ctx`` keys: mission_id, command_id, incident_id, device_id (rover),
    zone_id, waypoint_id, target_device_id, pose, started_epoch,
    completed_epoch (optional).
    """
    started = float(ctx.get("started_epoch") or 0.0)
    base = {
        "report_id": f"insp-{ctx.get('mission_id', 'unknown')}-{int(started * 1000)}",
        "incident_id": str(ctx.get("incident_id", "")),
        "mission_id": str(ctx.get("mission_id", "")),
        "command_id": str(ctx.get("command_id", "")),
        "device_id": str(ctx.get("device_id", "")),
        "target_device_id": str(ctx.get("target_device_id", "")),
        "cabinet_id": "",
        "zone_id": str(ctx.get("zone_id", "")),
        "waypoint_id": str(ctx.get("waypoint_id", "")),
        "pose": dict(ctx.get("pose") or {}),
        "started_epoch": started,
        "completed_epoch": float(ctx.get("completed_epoch") or started),
        "status": STATUS_ERROR,
        "status_detail": "",
        "adapter": "",
        "provenance": "DEMO",
        "synthetic": True,
        "checks": [],
        "observations": [],
        "evidence_refs": [],
    }
    base.update(fields)
    return InspectionReport(**base)


def compute_status(checks: list) -> str:
    """Aggregate per-check results into a report status (fail-closed)."""
    if not checks:
        return STATUS_OK
    ok = sum(1 for c in checks if c.get("ok"))
    if ok == len(checks):
        return STATUS_OK
    if ok == 0:
        return STATUS_UNREACHABLE
    return STATUS_DEGRADED


class InspectionEvidenceStore:
    """Writes inspection report artifacts + evidence-meta sidecars.

    Layout mirrors ``ArtifactStore``: ``<root>/<zone_id>/<artifact>.json``
    (the report) plus ``<artifact>.meta.json`` (sha256/bytes/storage_ref —
    the pointer downstream consumers and ``evidence_to_common`` need).
    """

    def __init__(self, root, retention_per_zone: int = 50):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.retention = retention_per_zone

    @staticmethod
    def _safe(name: str) -> str:
        return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)[:96]

    def store(self, report: InspectionReport) -> dict:
        """Persist the report; returns the evidence-meta mapping."""
        zone_dir = self.root / self._safe(report.zone_id or "unknown")
        zone_dir.mkdir(parents=True, exist_ok=True)
        artifact_id = self._safe(report.report_id)
        report_path = zone_dir / f"{artifact_id}.json"
        meta_path = zone_dir / f"{artifact_id}.meta.json"

        body = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
        report_path.write_text(body)
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        size = len(body.encode("utf-8"))

        meta = {
            "artifact_id": artifact_id,
            "kind": REPORT_KIND,
            "mission_id": report.mission_id,
            "command_id": report.command_id,
            "device_id": report.device_id,
            "zone_id": report.zone_id,
            "waypoint_id": report.waypoint_id,
            "incident_id": report.incident_id,
            "target_device_id": report.target_device_id,
            "cabinet_id": report.cabinet_id,
            "status": report.status,
            "adapter": report.adapter,
            "observed_at": report.completed_at,
            "received_at": report.completed_at,
            "storage_ref": str(report_path),
            "path": str(report_path),
            "sha256": digest,
            "bytes": size,
            "synthetic": report.synthetic,
            "provenance": report.provenance,
            "pose": report.pose,
            "evidence_refs": report.evidence_refs,
        }
        meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
        self._enforce_retention(zone_dir)
        return meta

    def _enforce_retention(self, zone_dir: Path) -> None:
        reports = sorted(
            (p for p in zone_dir.glob("*.json")
             if not p.name.endswith(".meta.json")),
            key=lambda p: p.stat().st_mtime, reverse=True)
        for old in reports[self.retention:]:
            old.unlink(missing_ok=True)
            old.with_name(old.name[:-5] + ".meta.json").unlink(missing_ok=True)
