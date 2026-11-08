"""Hardware autonomy compatibility adapter.

Maps an authorized ``inspect_zone`` checkpoint to the physical rover
autonomy command contract::

    {"mission_id": "inspection-001",
     "action": "inspect_cabinet",
     "cabinet_id": "rack-02"}

Boundary rules:

- ``cabinet_id`` comes ONLY from the registered inspection target
  (``config/inspection_targets.json`` via ``InspectionRegistry``). The
  adapter never derives it from camera markers, AprilTag payloads, or
  sticker types — physical marker recognition stays independent of
  sticker type, and navigation/autonomy code is untouched.
- ``mission_id`` is preserved verbatim for correlation and
  deduplication; a hardware response echoing a different mission_id is
  rejected as ``mission_id_mismatch`` evidence, never trusted.
- ``cabinet_id`` is re-validated against the registry allowlist
  (``InspectionRegistry.cabinet_ids()``) before a command is built —
  the same fail-closed pattern as ``LiveNetworkInspector``.
- Responses are normalized into the shared ``InspectionReport`` evidence
  shape, so they flow through the existing hashed artifact store and
  ``sentinel.rover.evidence`` telemetry unchanged.

Transports:

- ``SimulatedHardwareTransport`` — deterministic canned responses for
  tests/sim (``provenance: DEMO``, ``synthetic: true``).
- A live transport is a future integration point; until one is bound,
  ``hardware_transport_from_name`` fails closed rather than pretending.
"""

from __future__ import annotations

import hashlib
import time
from typing import Mapping, Optional, Protocol

from .inspection import (
    REPORT_STATUSES,
    STATUS_DEGRADED,
    STATUS_ERROR,
    STATUS_OK,
    STATUS_UNREACHABLE,
    InspectionReport,
    InspectionTarget,
    new_report,
)
from .models import parse_iso_utc
from .netinspect import InspectionDenied

ACTION_INSPECT_CABINET = "inspect_cabinet"

# Response statuses the autonomy side may return. "duplicate" means the
# mission_id was already executed — dedup evidence, mapped to ok below.
_HW_RESPONSE_STATUSES = REPORT_STATUSES | {"duplicate"}


class HardwareTimeout(Exception):
    """Transport exceeded its bounded wait — treat as unreachable."""


class HardwareUnavailable(Exception):
    """No transport bound for the requested mode — fail closed."""


class HardwareTransport(Protocol):
    """send() contract: one command dict in, one response dict out.

    Implementations MUST bound their own wait (timeout); the adapter
    records wall latency but never blocks indefinitely on a transport
    that ignores its contract.
    """

    name: str
    provenance: str
    synthetic: bool

    def send(self, command: Mapping) -> Mapping: ...


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _sha(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Simulated transport — deterministic responses, no hardware, no network.
# ---------------------------------------------------------------------------

class SimulatedHardwareTransport:
    """Scripted autonomy responses keyed by cabinet_id.

    ``scenarios`` maps cabinet_id -> scenario dict:

      status: str            ok|degraded|unreachable|error|duplicate
      detail: str            free-text detail echoed into the response
      checks: [{name,ok,detail,latency_ms}]   verbatim check override
      check_status: {name: ok|fail|timeout}   per-check override
      evidence: [...]        verbatim evidence_refs override
      latency_ms: int        reported round-trip latency
      timeout: true          raise HardwareTimeout (bounded wait expiry)
      malformed: true        return a response missing mission_id
      age_s: float           backdate completed_at (stale-result path)
    """

    name = "simulated-hw"
    provenance = "DEMO"
    synthetic = True

    DEFAULT_CHECKS = (
        ("cabinet_present", "cabinet pose confirmed within tolerance"),
        ("contact_sensors", "door/contact sensor snapshot"),
        ("environmental", "temp/humidity probe"),
        ("still_capture", "cabinet still captured on Pi"),
        ("pi_heartbeat", "cabinet Pi heartbeat"),
    )

    def __init__(self, scenarios: Optional[Mapping] = None,
                 clock=time.time, seed: str = "sim-hw-adapter"):
        self.scenarios = dict(scenarios or {})
        self.clock = clock
        self.seed = seed
        self.sent: list = []          # every command received (test hook)

    def send(self, command: Mapping) -> Mapping:
        self.sent.append(dict(command))
        cabinet_id = str(command.get("cabinet_id", ""))
        mission_id = str(command.get("mission_id", ""))
        scenario = self.scenarios.get(cabinet_id, {})

        if scenario.get("timeout"):
            raise HardwareTimeout(f"no response from {cabinet_id}")

        started = self.clock()
        completed = self.clock()
        age = scenario.get("age_s")
        if age:
            completed -= float(age)

        checks = scenario.get("checks")
        if checks is None:
            overrides = scenario.get("check_status") or {}
            status_forced = scenario.get("status")
            unreachable = status_forced == "unreachable"
            checks = []
            for name, detail in self.DEFAULT_CHECKS:
                override = overrides.get(name)
                if unreachable or override in ("fail", "timeout"):
                    ok, d = False, "unreachable" if unreachable else str(override)
                else:
                    ok, d = True, detail
                checks.append({
                    "name": name, "ok": ok, "detail": d,
                    "latency_ms": int.from_bytes(hashlib.sha256(
                        f"{self.seed}:{cabinet_id}:{name}".encode()
                    ).digest()[:2], "big") % 40 + 5,
                })

        evidence = scenario.get("evidence")
        if evidence is None:
            evidence = [
                {"kind": "cabinet_still",
                 "ref": f"cabinet://{cabinet_id}/{mission_id}/still-1.jpg",
                 "sha256": _sha(f"{self.seed}:still:{mission_id}")},
                {"kind": "sensor_snapshot",
                 "ref": f"cabinet://{cabinet_id}/{mission_id}/sensors.json",
                 "sha256": _sha(f"{self.seed}:sensors:{mission_id}")},
            ]

        resp = {
            "schema_version": 1,
            "mission_id": "" if scenario.get("malformed") else mission_id,
            "cabinet_id": cabinet_id,
            "action": ACTION_INSPECT_CABINET,
            "status": str(scenario.get("status", "ok")),
            "detail": str(scenario.get("detail", "")),
            "target_device_id": f"pi-{cabinet_id}",
            "started_at": _iso(started),
            "completed_at": _iso(completed),
            "latency_ms": int(scenario.get("latency_ms", 0)),
            "checks": checks,
            "evidence": evidence,
            "provenance": "LIVE",   # what real hardware would claim; adapter
                                    # overrides with transport provenance
        }
        return resp


class UnconfiguredHardwareTransport:
    """Placeholder until a live autonomy link is bound — always refuses."""

    name = "unconfigured"
    provenance = "LIVE"
    synthetic = False

    def send(self, command: Mapping) -> Mapping:
        raise HardwareUnavailable(
            "no live hardware transport bound (ROVER_HARDWARE_TRANSPORT)")


def hardware_transport_from_name(name: str, *, scenarios: Optional[Mapping] = None,
                                 clock=time.time) -> HardwareTransport:
    """Factory for CLI wiring. Unknown names fail closed."""
    if name in ("sim", "simulated"):
        return SimulatedHardwareTransport(scenarios=scenarios, clock=clock)
    if name in ("live", "esp32", "serial"):
        # Reserved for the hardware engineer's autonomy link — not bound yet.
        return UnconfiguredHardwareTransport()
    raise ValueError(f"unknown hardware transport {name!r} (sim|live)")


# ---------------------------------------------------------------------------
# Adapter — authorized inspect_zone checkpoint -> inspect_cabinet command.
# ---------------------------------------------------------------------------

def build_cabinet_command(mission_id: str, cabinet_id: str) -> dict:
    """The exact autonomy command shape. mission_id is preserved verbatim —
    the hardware side dedups on it; no other fields are added."""
    return {
        "mission_id": str(mission_id),
        "action": ACTION_INSPECT_CABINET,
        "cabinet_id": str(cabinet_id),
    }


class HardwareCabinetInspector:
    """NetworkInspector-protocol adapter delegating to the autonomy command.

    ``allowed_cabinets`` is the registry-derived allowlist
    (``InspectionRegistry.cabinet_ids()``); anything outside it is denied
    before a command is even built.
    """

    name = "hardware"

    def __init__(self, allowed_cabinets, transport: HardwareTransport,
                 clock=time.time):
        self.allowed_cabinets = frozenset(allowed_cabinets)
        self.transport = transport
        self.clock = clock
        self.provenance = getattr(transport, "provenance", "DEMO")
        self.synthetic = bool(getattr(transport, "synthetic", True))

    # -- response normalization -------------------------------------------
    @staticmethod
    def _parse_ts(value, fallback: float) -> float:
        if not isinstance(value, str) or not value:
            return fallback
        try:
            return parse_iso_utc(value)
        except (ValueError, TypeError):
            return fallback

    @staticmethod
    def _norm_checks(raw) -> list:
        out = []
        if not isinstance(raw, list):
            return out
        for c in raw:
            if not isinstance(c, Mapping):
                continue
            name = c.get("name")
            if not isinstance(name, str) or not name:
                continue
            out.append({
                "name": name,
                "type": "hardware",
                "ok": bool(c.get("ok")),
                "latency_ms": int(c.get("latency_ms") or 0),
                "detail": str(c.get("detail", ""))[:200],
            })
        return out

    @staticmethod
    def _norm_evidence(raw) -> list:
        out = []
        if not isinstance(raw, list):
            return out
        for e in raw:
            if not isinstance(e, Mapping):
                continue
            ref = e.get("ref") or e.get("uri") or e.get("storage_ref")
            if not isinstance(ref, str) or not ref:
                continue
            out.append({
                "kind": str(e.get("kind", "artifact")),
                "ref": ref[:300],
                "sha256": str(e.get("sha256", ""))[:64],
            })
        return out

    def _error_report(self, ctx: Mapping, cabinet_id: str, detail: str,
                      started: float, completed: float) -> InspectionReport:
        return new_report(
            ctx, target_device_id=str(ctx.get("target_device_id", "")),
            cabinet_id=cabinet_id, status=STATUS_ERROR,
            status_detail=detail[:200], adapter=self.name,
            provenance=self.provenance, synthetic=self.synthetic,
            started_epoch=started, completed_epoch=completed)

    # -- NetworkInspector protocol -----------------------------------------
    def inspect(self, target: InspectionTarget, ctx: Mapping) -> InspectionReport:
        cabinet_id = target.cabinet_id
        if not cabinet_id:
            raise InspectionDenied(
                f"target {target.device_id} has no registered cabinet_id")
        if cabinet_id not in self.allowed_cabinets:
            raise InspectionDenied(
                f"cabinet_id not allowlisted: {cabinet_id}")

        command = build_cabinet_command(ctx.get("mission_id", ""), cabinet_id)
        started = self.clock()

        try:
            resp = self.transport.send(command)
        except HardwareTimeout:
            return new_report(
                ctx, target_device_id=target.device_id,
                cabinet_id=cabinet_id, status=STATUS_UNREACHABLE,
                status_detail="hardware_timeout", adapter=self.name,
                provenance=self.provenance, synthetic=self.synthetic,
                started_epoch=started, completed_epoch=self.clock())
        except HardwareUnavailable as exc:
            raise InspectionDenied(str(exc))
        except Exception as exc:
            return self._error_report(
                ctx, cabinet_id, f"transport_error:{exc.__class__.__name__}",
                started, self.clock())

        completed = self.clock()
        if not isinstance(resp, Mapping):
            return self._error_report(ctx, cabinet_id, "malformed_response",
                                      started, completed)

        # Correlation + dedup guard: the autonomy side MUST echo the exact
        # mission_id it executed. A mismatch means the response belongs to
        # a different mission — record it as error evidence, never merge.
        if resp.get("mission_id") != command["mission_id"]:
            return self._error_report(
                ctx, cabinet_id,
                f"mission_id_mismatch:{resp.get('mission_id')!r}"[:200],
                started, completed)
        resp_cabinet = resp.get("cabinet_id")
        if resp_cabinet is not None and resp_cabinet != cabinet_id:
            return self._error_report(
                ctx, cabinet_id,
                f"cabinet_id_mismatch:{resp_cabinet!r}"[:200],
                started, completed)

        raw_status = str(resp.get("status", ""))
        if raw_status == "duplicate":
            # mission_id already executed autonomy-side — dedup evidence.
            status, detail = STATUS_OK, "duplicate_mission_suppressed"
        elif raw_status in REPORT_STATUSES:
            status, detail = raw_status, str(resp.get("detail", ""))
        else:
            return self._error_report(
                ctx, cabinet_id, f"unknown_status:{raw_status!r}"[:200],
                started, completed)

        checks = self._norm_checks(resp.get("checks"))
        if raw_status in (STATUS_OK, STATUS_DEGRADED) and checks:
            # Trust but verify: a claimed-ok response with failed checks is
            # downgraded, never upgraded.
            if not all(c["ok"] for c in checks):
                status = (STATUS_DEGRADED if any(c["ok"] for c in checks)
                          else STATUS_UNREACHABLE)
        evidence_refs = self._norm_evidence(
            resp.get("evidence", resp.get("artifacts")))

        # Hardware-reported timestamps are kept verbatim — including
        # legitimately old completed_at values, which the service's
        # freshness gate (is_stale) relies on to flag stale results.
        started_epoch = self._parse_ts(resp.get("started_at"), started)
        completed_epoch = self._parse_ts(resp.get("completed_at"), completed)

        return new_report(
            ctx,
            target_device_id=target.device_id,
            cabinet_id=cabinet_id,
            report_id=f"insp-hw-{ctx.get('mission_id', 'unknown')}-{int(started * 1000)}",
            started_epoch=started_epoch,
            completed_epoch=completed_epoch,
            status=status,
            status_detail=detail[:200],
            adapter=self.name,
            provenance=self.provenance,
            synthetic=self.synthetic,
            checks=checks,
            observations=[],
            evidence_refs=evidence_refs,
        )
