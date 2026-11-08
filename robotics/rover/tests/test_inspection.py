"""Checkpoint network inspection — inspect_zone -> registered Pi ->
simulated wireless observations + allowlisted health checks -> hashed
structured evidence -> mission telemetry/common evidence.

Covers: mission success, invalid targets, unreachable devices, stale
results, duplicate requests, sensor failures, live-adapter allowlist and
bounded timeouts, and evidence integration mapping.
"""

import hashlib
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from rover_mission.camera import SyntheticCamera
from rover_mission.common import (
    common_to_module_evidence_row,
    validate_common_evidence,
)
from rover_mission.inspection import (
    InspectionRegistry,
    InspectionTarget,
    validate_check_spec,
)
from rover_mission.localization import NoopDetector
from rover_mission.models import MissionState, MissionType
from rover_mission.netinspect import (
    InspectionDenied,
    InspectionSensorError,
    LiveNetworkInspector,
    SimulatedNetworkInspector,
    inspector_from_name,
)
from rover_mission.service import RoverService, ServiceConfig
from rover_mission.telemetry import ConsolePublisher

from conftest import DEVICE, SECRET, run_until_done, signed

TARGETS_JSON = {
    "device_id": DEVICE,
    "targets": [
        {
            "device_id": "pi-test-01", "zone_id": "zone-a",
            "waypoint_id": "wp-b", "address": "10.9.9.21",
            "ssid": "TEST-PI-01", "bssid": "02:aa:bb:cc:dd:01",
            "label": "Test Pi at wp-b",
            "checks": [
                {"type": "ping"},
                {"type": "tcp_connect", "port": 22},
                {"type": "http_health", "port": 8080, "path": "/healthz"},
            ],
        },
        {
            "device_id": "pi-test-02", "zone_id": "zone-b",
            "waypoint_id": "wp-far", "address": "10.9.9.22",
            "checks": [{"type": "tcp_connect", "port": 22}],
        },
    ],
}


@pytest.fixture
def registry(tmp_path):
    p = tmp_path / "inspection_targets.json"
    p.write_text(json.dumps(TARGETS_JSON))
    return InspectionRegistry.load(p)


def make_service(route_map, link, clock, tmp_path, registry,
                 scenarios=None, inspector=None):
    events = open(tmp_path / "events.jsonl", "w")
    return RoverService(
        route_map, link,
        camera=SyntheticCamera(), detector=NoopDetector(),
        publisher=ConsolePublisher(stream=events),
        config=ServiceConfig(device_id=DEVICE, secret=SECRET,
                             evidence_dir=str(tmp_path / "evidence")),
        clock=clock,
        inspector=inspector or SimulatedNetworkInspector(
            scenarios=scenarios, clock=clock),
        inspection_registry=registry,
    )


@pytest.fixture
def pi_service(route_map, link, clock, tmp_path, registry):
    return make_service(route_map, link, clock, tmp_path, registry)


def inspect_mission(clock, mission_id="insp-m1", command_id="insp-c1",
                    waypoint="wp-b", zone="zone-a", **fields):
    return signed(MissionType.INSPECT_ZONE, mission_id, command_id, clock,
                  zone_id=zone, waypoint_id=waypoint, **fields)


def inspection_reports(evidence_dir: Path) -> list[dict]:
    return [json.loads(p.read_text())
            for p in sorted(Path(evidence_dir).rglob("insp-*.json"))
            if not p.name.endswith(".meta.json")]


def read_events(tmp_path) -> list[dict]:
    f = tmp_path / "events.jsonl"
    if not f.exists():
        return []
    return [json.loads(line) for line in f.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Mission success path
# ---------------------------------------------------------------------------

def test_inspect_zone_completes_with_network_inspection(
        pi_service, link, clock, tmp_path):
    ok, reason, rec = pi_service.submit(inspect_mission(
        clock, incident_id="inc-77"))
    assert ok, reason
    run_until_done(pi_service, link, clock)
    final = pi_service.missions[-1]
    assert final.state == MissionState.COMPLETED, final.reason
    assert final.reason.startswith("inspection_")
    assert final.incident_id == "inc-77"

    # --- structured report ---
    assert len(pi_service.inspection_reports) == 1
    report = pi_service.inspection_reports[0]
    assert report.status == "ok"
    assert report.target_device_id == "pi-test-01"
    assert report.mission_id == "insp-m1"
    assert report.incident_id == "inc-77"
    assert report.adapter == "simulated"
    assert report.provenance == "DEMO"
    assert report.synthetic is True
    assert len(report.checks) == 3
    assert all(c["ok"] for c in report.checks)
    kinds = {o["kind"] for o in report.observations}
    assert {"wifi_ap_seen", "wifi_probe", "device_health"} <= kinds
    for o in report.observations:
        assert o["schema_version"] == 1
        assert o["device_id"] == DEVICE      # rover observed, Pi is target
        assert o["zone_id"] == "zone-a"

    # --- hashed artifact on disk ---
    reports = inspection_reports(tmp_path / "evidence")
    assert len(reports) == 1
    body = reports[0]
    assert body["kind"] == "network_inspection"
    assert body["target_device_id"] == "pi-test-01"
    meta_files = list((tmp_path / "evidence").rglob("insp-*.meta.json"))
    assert len(meta_files) == 1
    meta = json.loads(meta_files[0].read_text())
    assert len(meta["sha256"]) == 64
    assert meta["synthetic"] is True and meta["provenance"] == "DEMO"
    assert meta["incident_id"] == "inc-77"
    # hash covers the exact artifact bytes
    artifact = Path(meta["storage_ref"])
    assert artifact.exists()
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == meta["sha256"]

    # --- common evidence mapping (downstream/Nemotron path) ---
    assert len(pi_service.inspection_evidence) == 1
    ev = pi_service.inspection_evidence[0]
    assert validate_common_evidence(ev) == (True, "")
    assert ev["synthetic"] is True and ev["provenance"] == "DEMO"
    row = common_to_module_evidence_row(
        ev, incident_id="inc-77", trust_tier="device", trace_id="tr-1")
    assert row["incidentId"] == "inc-77"
    assert row["sha256"] == meta["sha256"]
    assert row["source"].startswith("rover/rover-01/")

    # --- telemetry events through existing publisher path ---
    events = read_events(tmp_path)
    names = [e["event"] for e in events]
    assert "inspection_started" in names
    assert "inspection_completed" in names
    done = next(e for e in events if e["event"] == "inspection_completed")
    assert done["status"] == "ok"
    assert done["target_device_id"] == "pi-test-01"
    assert done["artifact_id"] == meta["artifact_id"]
    assert done["sha256"] == meta["sha256"]
    assert done["incident_id"] == "inc-77"
    assert done["zone_id"] == "zone-a"

    # --- photo evidence still hashed + synthetic-labeled alongside ---
    photo_meta = list((tmp_path / "evidence").rglob("ev-*.json"))
    assert photo_meta, "capture waypoint should still produce photo evidence"
    pm = json.loads(photo_meta[-1].read_text())
    assert pm["synthetic"] is True
    assert hashlib.sha256(
        Path(pm["storage_ref"]).read_bytes()).hexdigest() == pm["sha256"]


def test_two_inspections_produce_independent_reports(
        pi_service, link, clock, tmp_path, registry):
    for i, wp in enumerate(["wp-b", "wp-far"]):
        zone = "zone-a" if wp == "wp-b" else "zone-b"
        ok, reason, _ = pi_service.submit(inspect_mission(
            clock, mission_id=f"insp-x{i}", command_id=f"insp-xc{i}",
            waypoint=wp, zone=zone))
        assert ok, reason
        run_until_done(pi_service, link, clock)
        assert pi_service.missions[-1].state == MissionState.COMPLETED
    assert len(pi_service.inspection_reports) == 2
    assert {r.target_device_id for r in pi_service.inspection_reports} == \
        {"pi-test-01", "pi-test-02"}
    assert len(inspection_reports(tmp_path / "evidence")) == 2


def test_patrol_does_not_run_network_inspection(
        pi_service, link, clock, tmp_path):
    ok, reason, _ = pi_service.submit(signed(
        MissionType.PATROL_ROUTE, "pat-insp", "cmd-pinsp", clock,
        route_id="loop-a"))
    assert ok, reason
    run_until_done(pi_service, link, clock)
    assert pi_service.missions[-1].state == MissionState.COMPLETED
    assert pi_service.inspection_reports == []
    assert inspection_reports(tmp_path / "evidence") == []


# ---------------------------------------------------------------------------
# Invalid / unregistered targets
# ---------------------------------------------------------------------------

def test_unknown_waypoint_rejected_before_motion(pi_service, link, clock):
    before = len(link.commands)
    ok, reason, _ = pi_service.submit(inspect_mission(
        clock, waypoint="wp-evil"))
    assert not ok and reason == "unknown_waypoint"
    run_until_done(pi_service, link, clock, max_ticks=10)
    assert len(link.commands) == before


def test_surveyed_but_unregistered_checkpoint(pi_service, link, clock,
                                              tmp_path):
    """wp-a is surveyed but has no registered Pi -> honest no-target report."""
    ok, reason, _ = pi_service.submit(inspect_mission(
        clock, waypoint="wp-a", mission_id="insp-notarget"))
    assert ok, reason
    run_until_done(pi_service, link, clock)
    final = pi_service.missions[-1]
    assert final.state == MissionState.COMPLETED
    report = pi_service.inspection_reports[-1]
    assert report.status == "no_registered_target"
    assert report.target_device_id == ""
    assert report.checks == [] and report.observations == []
    assert inspection_reports(tmp_path / "evidence")


def test_registry_rejects_bad_config(tmp_path):
    bad_checks = {"device_id": DEVICE, "targets": [
        {"device_id": "pi-x", "zone_id": "zone-a", "waypoint_id": "wp-a",
         "address": "10.0.0.9", "checks": [{"type": "nmap"}]}]}
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad_checks))
    with pytest.raises(ValueError, match="check_type_not_allowlisted"):
        InspectionRegistry.load(p)

    dup = {"device_id": DEVICE, "targets": [
        {"device_id": "pi-x", "zone_id": "zone-a", "waypoint_id": "wp-a",
         "address": "10.0.0.9"},
        {"device_id": "pi-y", "zone_id": "zone-a", "waypoint_id": "wp-a",
         "address": "10.0.0.10"}]}
    p.write_text(json.dumps(dup))
    with pytest.raises(ValueError, match="duplicate"):
        InspectionRegistry.load(p)


def test_check_spec_bounds():
    assert validate_check_spec({"type": "nmap"})[0] is False
    assert validate_check_spec({"type": "tcp_connect", "port": 0})[0] is False
    assert validate_check_spec({"type": "tcp_connect", "port": 70000})[0] is False
    assert validate_check_spec(
        {"type": "http_health", "port": 80, "path": "no-slash"})[0] is False
    assert validate_check_spec(
        {"type": "http_health", "port": 80, "path": "/a b"})[0] is False
    assert validate_check_spec({"type": "ping"})[0] is True
    assert validate_check_spec(
        {"type": "http_health", "port": 8080, "path": "/healthz"})[0] is True


# ---------------------------------------------------------------------------
# Unreachable / stale / sensor failure / denied
# ---------------------------------------------------------------------------

def test_unreachable_device_reported_as_evidence(
        route_map, link, clock, tmp_path, registry):
    svc = make_service(route_map, link, clock, tmp_path, registry,
                       scenarios={"pi-test-01": {"reachable": False}})
    ok, _, _ = svc.submit(inspect_mission(clock))
    assert ok
    run_until_done(svc, link, clock)
    assert svc.missions[-1].state == MissionState.COMPLETED
    report = svc.inspection_reports[-1]
    assert report.status == "unreachable"
    assert all(not c["ok"] for c in report.checks)
    assert all(c["detail"] == "unreachable" for c in report.checks)
    assert any(o["kind"] == "device_offline" for o in report.observations)
    assert svc.missions[-1].reason == "inspection_unreachable"


def test_stale_result_flagged(route_map, link, clock, tmp_path, registry):
    svc = make_service(route_map, link, clock, tmp_path, registry,
                       scenarios={"pi-test-01": {"stale_s": 400}})
    ok, _, _ = svc.submit(inspect_mission(clock))
    assert ok
    run_until_done(svc, link, clock)
    report = svc.inspection_reports[-1]
    assert report.status == "stale"
    assert "result_age_s" in report.status_detail
    assert svc.missions[-1].reason == "inspection_stale"
    # stale evidence is still stored + published, honestly labeled
    assert inspection_reports(tmp_path / "evidence")
    assert svc.inspection_evidence[-1]["artifact_id"] == report.report_id


def test_sensor_failure_degrades_to_error_evidence(
        route_map, link, clock, tmp_path, registry):
    svc = make_service(route_map, link, clock, tmp_path, registry,
                       scenarios={"pi-test-01": {"sensor_error": "radio_dead"}})
    ok, _, _ = svc.submit(inspect_mission(clock))
    assert ok
    run_until_done(svc, link, clock)
    final = svc.missions[-1]
    assert final.state == MissionState.COMPLETED  # nav+photo still honest
    report = svc.inspection_reports[-1]
    assert report.status == "error"
    assert "radio_dead" in report.status_detail
    assert inspection_reports(tmp_path / "evidence")


def test_live_adapter_denies_unlisted_target(
        route_map, link, clock, tmp_path, registry):
    live = LiveNetworkInspector(allowed_addresses=frozenset({"10.0.0.1"}))
    svc = make_service(route_map, link, clock, tmp_path, registry,
                       inspector=live)
    ok, _, _ = svc.submit(inspect_mission(clock))
    assert ok
    run_until_done(svc, link, clock)
    report = svc.inspection_reports[-1]
    assert report.status == "denied"
    assert "allowlist" in report.status_detail
    # nothing was probed: no checks ran
    assert report.checks == []


def test_duplicate_mission_rejected(pi_service, link, clock):
    m = inspect_mission(clock, mission_id="dup-1", command_id="dup-c1")
    ok, _, _ = pi_service.submit(m)
    assert ok
    # exact replay — same signed dict
    ok2, reason2, _ = pi_service.submit(m)
    assert not ok2 and reason2 == "duplicate_mission"
    # different mission_id but replayed command_id also rejected
    m2 = inspect_mission(clock, mission_id="dup-2", command_id="dup-c1")
    ok3, reason3, _ = pi_service.submit(m2)
    assert not ok3 and reason3 == "duplicate_mission"
    # and after completion the id is still burned (idempotent ingest)
    run_until_done(pi_service, link, clock)
    ok4, reason4, _ = pi_service.submit(m)
    assert not ok4 and reason4 == "duplicate_mission"
    assert len(pi_service.missions) == 1


# ---------------------------------------------------------------------------
# Live adapter: allowlist, check validation, bounded real probes
# ---------------------------------------------------------------------------

def _target(address="127.0.0.1", checks=None, device_id="pi-live-01"):
    return InspectionTarget(
        device_id=device_id, zone_id="zone-a", waypoint_id="wp-b",
        address=address,
        checks=tuple(checks or [{"type": "tcp_connect", "port": 22}]))


def _ctx():
    return {"mission_id": "live-1", "command_id": "live-c1",
            "incident_id": "", "device_id": DEVICE, "zone_id": "zone-a",
            "waypoint_id": "wp-b", "target_device_id": "pi-live-01",
            "pose": {}, "started_epoch": time.time()}


def test_live_inspector_denies_non_allowlisted_address():
    insp = LiveNetworkInspector(allowed_addresses=frozenset({"10.0.0.1"}))
    with pytest.raises(InspectionDenied, match="allowlist"):
        insp.inspect(_target(address="192.0.2.1"), _ctx())


def test_live_inspector_rejects_non_allowlisted_check():
    insp = LiveNetworkInspector(allowed_addresses=frozenset({"127.0.0.1"}))
    t = _target(checks=[{"type": "nmap", "port": 22}])
    with pytest.raises(InspectionDenied, match="check spec"):
        insp.inspect(t, _ctx())


def test_live_tcp_connect_bounded_probe():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    insp = LiveNetworkInspector(
        allowed_addresses=frozenset({"127.0.0.1"}), timeout_s=1.0)
    t = _target(checks=[{"type": "tcp_connect", "port": port}])
    report = insp.inspect(t, _ctx())
    listener.close()
    assert report.provenance == "LIVE" and report.synthetic is False
    assert report.status == "ok"
    check = report.checks[0]
    assert check["ok"] is True and check["latency_ms"] < 1000

    # closed port -> bounded failure, never an exception
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    dead_port = closed.getsockname()[1]
    closed.close()
    t2 = _target(checks=[{"type": "tcp_connect", "port": dead_port}])
    report2 = insp.inspect(t2, _ctx())
    assert report2.checks[0]["ok"] is False
    assert report2.checks[0]["detail"] in ("refused", "timeout")


def test_live_http_health_probe():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/healthz":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        insp = LiveNetworkInspector(
            allowed_addresses=frozenset({"127.0.0.1"}), timeout_s=1.0)
        t = _target(checks=[
            {"type": "http_health", "port": port, "path": "/healthz"}])
        report = insp.inspect(t, _ctx())
        assert report.checks[0]["ok"] is True
        assert report.checks[0]["detail"] == "http_200"
        t404 = _target(checks=[
            {"type": "http_health", "port": port, "path": "/nope"}])
        report404 = insp.inspect(t404, _ctx())
        assert report404.checks[0]["ok"] is False
        assert report404.checks[0]["detail"] == "http_404"
    finally:
        server.shutdown()


def test_live_probe_unreachable_is_bounded():
    insp = LiveNetworkInspector(
        allowed_addresses=frozenset({"192.0.2.1"}), timeout_s=0.3,
        max_timeout_s=0.5)
    t = _target(address="192.0.2.1",
                checks=[{"type": "tcp_connect", "port": 65000}])
    start = time.monotonic()
    report = insp.inspect(t, _ctx())
    elapsed = time.monotonic() - start
    assert elapsed < 5.0            # hard bound, never hangs the loop
    assert report.checks[0]["ok"] is False
    assert report.status in ("unreachable", "degraded")


# ---------------------------------------------------------------------------
# Adapter factory + simulated sensor error type
# ---------------------------------------------------------------------------

def test_inspector_factory():
    assert isinstance(inspector_from_name("sim"), SimulatedNetworkInspector)
    assert isinstance(inspector_from_name("live",
                                          allowed_addresses={"10.0.0.1"}),
                      LiveNetworkInspector)
    with pytest.raises(ValueError):
        inspector_from_name("carrier-pigeon")


def test_simulated_sensor_error_raises():
    insp = SimulatedNetworkInspector(
        scenarios={"pi-x": {"sensor_error": "dead"}})
    t = InspectionTarget(device_id="pi-x", zone_id="z", waypoint_id="w",
                         address="10.0.0.1")
    with pytest.raises(InspectionSensorError):
        insp.inspect(t, _ctx())
