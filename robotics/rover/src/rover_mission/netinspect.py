"""Modular network inspection adapters.

``NetworkInspector`` is the seam between the mission runtime and whatever
performs the actual checks:

- ``SimulatedNetworkInspector`` — deterministic, hardware-free. Produces
  simulated wireless observations (canonical observation shape, honestly
  labeled ``synthetic``/``DEMO``) plus scripted health-check outcomes.
- ``LiveNetworkInspector`` — real bounded probes (TCP connect, HTTP health,
  ping) against **allowlisted targets and check types only**, each with a
  hard timeout. Refuses anything outside the registry allowlist.

Wireless (RF) observations stay simulated until the monitor-mode
interceptor path is bound to missions — the live adapter covers network
health checks only. Neither adapter can touch motors: they are pure
observation/probe code (docs/03, docs/08).
"""

from __future__ import annotations

import hashlib
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from typing import Mapping, Optional, Protocol

from .inspection import (
    REPORT_STATUSES,
    InspectionReport,
    InspectionTarget,
    check_name,
    compute_status,
    new_report,
    validate_check_spec,
)


class InspectionDenied(Exception):
    """Adapter refused the target/check — fail closed, never probe."""


class InspectionSensorError(Exception):
    """Simulated sensor fault injected by a scenario."""


class NetworkInspector(Protocol):
    """inspect() contract. ``ctx`` carries mission/rover context:

    mission_id, command_id, incident_id, device_id (rover), zone_id,
    waypoint_id, target_device_id, pose, started_epoch.
    """

    name: str
    provenance: str
    synthetic: bool

    def inspect(self, target: InspectionTarget, ctx: Mapping) -> InspectionReport: ...


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _derive_mac(seed: str, *parts: str) -> str:
    """Deterministic locally-administered MAC from seed material."""
    digest = hashlib.sha256(":".join((seed, *parts)).encode()).digest()
    return "02:" + ":".join(f"{b:02x}" for b in digest[:5])


# ---------------------------------------------------------------------------
# Simulated adapter — deterministic scenarios, no hardware, no network.
# ---------------------------------------------------------------------------

class SimulatedNetworkInspector:
    """Scripted inspector for tests/sim runs.

    ``scenarios`` maps target device_id -> scenario dict:

      reachable: false            all checks fail 'unreachable'
      check_status: {name: state} per-check override
                                   (ok|fail|timeout|refused|error)
      latency_ms: int             fixed latency for all checks
      status: str                 force report status
      sensor_error: str|true      raise InspectionSensorError
      stale_s: float              backdate completed_epoch (stale result)
      observations: [...]         verbatim observation list override
      rssi_dbm / channel: int     observation radio parameters
    """

    name = "simulated"
    provenance = "DEMO"
    synthetic = True

    def __init__(self, scenarios: Optional[Mapping] = None,
                 clock=time.time, seed: str = "sim-netinspect"):
        self.scenarios = dict(scenarios or {})
        self.clock = clock
        self.seed = seed
        self._obs_seq = 0

    # -- observation helpers ---------------------------------------------
    def _next_seq(self, epoch: float) -> int:
        self._obs_seq += 1
        return int(epoch * 1_000_000) + self._obs_seq

    def _observation(self, observer_id: str, zone_id: str, kind: str,
                     epoch: float, data: dict) -> dict:
        return {
            "schema_version": 1,
            "event_id": f"evt-insp-{uuid.uuid4().hex[:12]}",
            "device_id": observer_id,
            "seq": self._next_seq(epoch),
            "observed_at": _iso(epoch),
            "kind": kind,
            "zone_id": zone_id,
            "data": data,
        }

    def _default_observations(self, target: InspectionTarget, ctx: Mapping,
                              epoch: float, reachable: bool,
                              scenario: Mapping) -> list:
        observer = str(ctx.get("device_id", ""))
        zone = str(ctx.get("zone_id", ""))
        ssid = target.ssid or f"{target.device_id}-wifi"
        bssid = target.bssid or _derive_mac(self.seed, target.device_id, "bssid")
        rssi = int(scenario.get("rssi_dbm", -58))
        channel = int(scenario.get("channel", 6))
        station = _derive_mac(self.seed, target.device_id, "station")
        return [
            self._observation(observer, zone, "wifi_ap_seen", epoch, {
                "bssid": bssid, "ssid": ssid, "rssi_dbm": rssi,
                "channel": channel, "frame_subtype": 8,
                "addr1": "ff:ff:ff:ff:ff:ff", "addr2": bssid, "addr3": bssid,
                "target_device_id": target.device_id,
            }),
            self._observation(observer, zone, "wifi_probe", epoch, {
                "bssid": bssid, "ssid": ssid, "probe_target": ssid,
                "rssi_dbm": rssi - 12, "channel": channel,
                "frame_subtype": 4,
                "addr1": bssid, "addr2": station, "addr3": bssid,
            }),
            self._observation(observer, zone,
                              "device_health" if reachable else "device_offline",
                              epoch, {
                "device_id": target.device_id, "address": target.address,
                "status": "reachable" if reachable else "unreachable",
            }),
        ]

    # -- checks ------------------------------------------------------------
    def _sim_check(self, target: InspectionTarget, spec: Mapping,
                   scenario: Mapping) -> dict:
        name = check_name(spec)
        overrides = scenario.get("check_status") or {}
        override = overrides.get(name)
        if scenario.get("reachable") is False:
            ok, detail = False, "unreachable"
        elif override in (None, "ok"):
            ok, detail = True, "ok"
        elif override in ("fail", "timeout", "refused", "error"):
            ok, detail = False, str(override)
        else:
            ok, detail = True, "ok"
        latency = int(scenario.get("latency_ms",
                                  int.from_bytes(
                                      hashlib.sha256(
                                          f"{self.seed}:{target.device_id}:{name}"
                                          .encode()).digest()[:2], "big") % 19 + 1))
        return {
            "name": name, "type": spec.get("type"), "ok": ok,
            "latency_ms": latency if ok else latency + 900,
            "detail": detail,
            "target": self._check_target(target, spec),
        }

    @staticmethod
    def _check_target(target: InspectionTarget, spec: Mapping) -> str:
        t = spec.get("type")
        if t == "tcp_connect":
            return f"{target.address}:{spec.get('port')}"
        if t == "http_health":
            return f"{target.address}:{spec.get('port')}{spec.get('path', '/healthz')}"
        return target.address

    # -- main ---------------------------------------------------------------
    def inspect(self, target: InspectionTarget, ctx: Mapping) -> InspectionReport:
        scenario = self.scenarios.get(target.device_id, {})
        if scenario.get("sensor_error"):
            detail = scenario["sensor_error"]
            raise InspectionSensorError(
                detail if isinstance(detail, str) and detail else "sensor_error")

        started = float(ctx.get("started_epoch") or self.clock())
        checks = [self._sim_check(target, spec, scenario)
                  for spec in target.checks]
        reachable = all(c["ok"] for c in checks)
        observations = scenario.get("observations")
        if observations is None:
            observations = self._default_observations(
                target, ctx, started, reachable, scenario)
        completed = self.clock()
        stale_s = scenario.get("stale_s")
        if stale_s:
            # Result finalized in the past — exercises the freshness gate.
            completed = completed - float(stale_s)
        forced = scenario.get("status")
        status = forced if forced in REPORT_STATUSES else compute_status(checks)
        return new_report(
            ctx,
            target_device_id=target.device_id,
            report_id=f"insp-{ctx.get('mission_id', 'unknown')}-{int(started * 1000)}",
            started_epoch=started, completed_epoch=completed,
            status=status, adapter=self.name, provenance=self.provenance,
            synthetic=self.synthetic, checks=checks,
            observations=list(observations),
        )


# ---------------------------------------------------------------------------
# Live adapter — bounded probes against allowlisted targets only.
# ---------------------------------------------------------------------------

class LiveNetworkInspector:
    """Real health checks with hard timeouts and a strict allowlist.

    - ``target.address`` must be in ``allowed_addresses`` (typically
      ``InspectionRegistry.addresses()``) or the target is denied outright.
    - Every check spec is re-validated against ``CHECK_TYPES`` — config
      load is not trusted as the only gate.
    - Each probe is bounded by ``timeout_s`` (clamped to ``max_timeout_s``);
      an overall ``max_total_s`` deadline skips remaining checks.
    - Wireless observations are NOT produced here — RF capture belongs to
      the monitor-mode interceptor path; this adapter reports ``[]``.
    """

    name = "live"
    provenance = "LIVE"
    synthetic = False

    def __init__(self, allowed_addresses, *, timeout_s: float = 2.0,
                 max_timeout_s: float = 5.0, max_total_s: float = 30.0,
                 clock=time.time):
        self.allowed_addresses = frozenset(allowed_addresses)
        self.timeout_s = min(float(timeout_s), float(max_timeout_s))
        self.max_timeout_s = float(max_timeout_s)
        self.max_total_s = float(max_total_s)
        self.clock = clock

    def inspect(self, target: InspectionTarget, ctx: Mapping) -> InspectionReport:
        if target.address not in self.allowed_addresses:
            raise InspectionDenied(
                f"target address {target.address} not in allowlist")
        for spec in target.checks:
            ok, reason = validate_check_spec(spec)
            if not ok:
                raise InspectionDenied(f"check spec rejected: {reason}")

        started = self.clock()
        deadline = started + self.max_total_s
        checks = []
        for spec in target.checks:
            if self.clock() > deadline:
                checks.append({
                    "name": check_name(spec), "type": spec.get("type"),
                    "ok": False, "latency_ms": 0,
                    "detail": "skipped_deadline",
                    "target": self._check_target(target, spec),
                })
                continue
            checks.append(self._execute_check(target, spec))
        completed = self.clock()
        return new_report(
            ctx,
            target_device_id=target.device_id,
            report_id=f"insp-{ctx.get('mission_id', 'unknown')}-{int(started * 1000)}",
            started_epoch=started, completed_epoch=completed,
            status=compute_status(checks), adapter=self.name,
            provenance=self.provenance, synthetic=self.synthetic,
            checks=checks, observations=[],
            status_detail="rf observations via interceptor path",
        )

    # -- probe executors (each bounded by self.timeout_s) -------------------
    def _execute_check(self, target: InspectionTarget, spec: Mapping) -> dict:
        name = check_name(spec)
        ttype = spec.get("type")
        started = time.monotonic()
        ok = False
        detail = ""
        try:
            if ttype == "tcp_connect":
                with socket.create_connection(
                        (target.address, int(spec["port"])),
                        timeout=self.timeout_s) as sock:
                    ok = True
                    detail = "connected"
            elif ttype == "http_health":
                path = spec.get("path", "/healthz")
                url = f"http://{target.address}:{int(spec['port'])}{path}"
                with urllib.request.urlopen(url, timeout=self.timeout_s) as resp:
                    code = int(getattr(resp, "status", resp.getcode()))
                    ok = 200 <= code < 400
                    detail = f"http_{code}"
            elif ttype == "ping":
                cp = subprocess.run(
                    ["ping", "-c", "1", target.address],
                    capture_output=True, timeout=self.timeout_s + 1.0)
                ok = cp.returncode == 0
                detail = "pong" if ok else f"ping_rc_{cp.returncode}"
        except urllib.error.HTTPError as exc:
            detail = f"http_{exc.code}"
        except (socket.timeout, TimeoutError):
            detail = "timeout"
        except ConnectionRefusedError:
            detail = "refused"
        except urllib.error.URLError as exc:
            detail = f"urlerror:{exc.reason}"
        except subprocess.TimeoutExpired:
            detail = "timeout"
        except OSError as exc:
            detail = f"oserror:{exc.__class__.__name__}"
        except Exception as exc:  # never let a probe crash the mission loop
            detail = f"error:{exc.__class__.__name__}"
        return {
            "name": name, "type": ttype, "ok": ok,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "detail": detail,
            "target": self._check_target(target, spec),
        }

    @staticmethod
    def _check_target(target: InspectionTarget, spec: Mapping) -> str:
        t = spec.get("type")
        if t == "tcp_connect":
            return f"{target.address}:{spec.get('port')}"
        if t == "http_health":
            return f"{target.address}:{spec.get('port')}{spec.get('path', '/healthz')}"
        return target.address


def inspector_from_name(name: str, *, allowed_addresses=(),
                        allowed_cabinets=(), clock=time.time,
                        scenarios: Optional[Mapping] = None,
                        hardware_transport=None) -> NetworkInspector:
    """Factory for CLI/programmatic wiring. Unknown names fail closed."""
    if name == "sim" or name == "simulated":
        return SimulatedNetworkInspector(scenarios=scenarios, clock=clock)
    if name == "live":
        return LiveNetworkInspector(allowed_addresses, clock=clock)
    if name in ("hardware", "hw", "hw-cabinet"):
        from .hw_adapter import (
            HardwareCabinetInspector,
            hardware_transport_from_name,
        )
        transport = hardware_transport or hardware_transport_from_name(
            "sim", scenarios=scenarios, clock=clock)
        return HardwareCabinetInspector(allowed_cabinets, transport,
                                        clock=clock)
    raise ValueError(
        f"unknown inspector {name!r} (sim|live|hardware)")
