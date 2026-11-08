"""Hardware autonomy compatibility adapter — inspect_zone ->
{mission_id, action: inspect_cabinet, cabinet_id} -> normalized
InspectionReport evidence.

Covers: command shape, mission_id preservation, cabinet_id registry
allowlist, simulated transport responses, unreachable/timeout/malformed/
duplicate/stale outcomes, evidence refs, and end-to-end service wiring.
"""

import hashlib
import json
from pathlib import Path

import pytest

from rover_mission.hw_adapter import (
    ACTION_INSPECT_CABINET,
    HardwareCabinetInspector,
    HardwareTimeout,
    HardwareUnavailable,
    HttpHardwareTransport,
    SimulatedHardwareTransport,
    UnconfiguredHardwareTransport,
    build_cabinet_command,
    hardware_transport_from_name,
)
from rover_mission.inspection import (
    InspectionRegistry,
    InspectionTarget,
)
from rover_mission.models import MissionState, MissionType
from rover_mission.netinspect import InspectionDenied, inspector_from_name
from rover_mission.service import RoverService, ServiceConfig
from rover_mission.camera import SyntheticCamera
from rover_mission.localization import NoopDetector
from rover_mission.telemetry import ConsolePublisher

from conftest import DEVICE, SECRET, run_until_done, signed


def test_async_hardware_waits_for_correlated_inspection_report():
    calls = []
    responses = iter([
        (202, {'mission_id': 'm1', 'state': 'accepted'}),
        (200, {'mission_id': 'm1', 'cabinet_id': 'rack-02', 'state': 'completed',
               'report': {'mission_id': 'm1', 'cabinet_id': 'rack-02', 'status': 'ok'}}),
    ])
    def opener(req, timeout):
        calls.append((req.get_method(), req.full_url, req.get_header('Authorization')))
        status, result = next(responses)
        return status, json.dumps(result).encode()
    transport = HttpHardwareTransport('http://127.0.0.1:8090/v1/missions', token='test', opener=opener)
    assert transport.send({'mission_id': 'm1', 'cabinet_id': 'rack-02'})['status'] == 'ok'
    assert calls == [('POST', 'http://127.0.0.1:8090/v1/missions', 'Bearer test'),
                     ('GET', 'http://127.0.0.1:8090/v1/missions/m1', 'Bearer test')]


def test_async_hardware_does_not_trust_completion_without_report():
    def opener(req, timeout):
        return 200, json.dumps({'mission_id': 'm1', 'cabinet_id': 'rack-02', 'state': 'completed'}).encode()
    transport = HttpHardwareTransport('http://127.0.0.1:8090/v1/missions', opener=opener)
    assert transport.send({'mission_id': 'm1'})['status'] == 'error'


def test_async_hardware_aborts_when_polling_fails():
    calls = []
    def opener(req, timeout):
        calls.append(req.get_method() + ' ' + req.full_url)
        if len(calls) == 1:
            return 202, b'{"mission_id":"m1","state":"accepted"}'
        if len(calls) == 2:
            raise OSError('disconnected')
        return 200, b'{}'
    transport = HttpHardwareTransport('http://127.0.0.1:8090/v1/missions', opener=opener)
    with pytest.raises(HardwareTimeout):
        transport.send({'mission_id': 'm1'})
    assert calls[-1].endswith('/v1/missions/m1/abort')

TARGETS_JSON = {
    "device_id": DEVICE,
    "targets": [
        {
            "device_id": "pi-test-01", "zone_id": "zone-a",
            "waypoint_id": "wp-b", "address": "10.9.9.21",
            "cabinet_id": "cab-test-01",
            "checks": [{"type": "ping"}],
        },
        {
            "device_id": "pi-test-02", "zone_id": "zone-b",
            "waypoint_id": "wp-far", "address": "10.9.9.22",
            # no cabinet_id — hardware adapter must deny this target
            "checks": [{"type": "ping"}],
        },
    ],
}


@pytest.fixture
def registry(tmp_path):
    p = tmp_path / "inspection_targets.json"
    p.write_text(json.dumps(TARGETS_JSON))
    return InspectionRegistry.load(p)


def make_hw_inspector(registry, clock, scenarios=None, transport=None):
    t = transport or SimulatedHardwareTransport(
        scenarios=scenarios, clock=clock)
    return HardwareCabinetInspector(registry.cabinet_ids(), t, clock=clock)


def make_service(route_map, link, clock, tmp_path, registry,
                 scenarios=None, transport=None):
    events = open(tmp_path / "events.jsonl", "w")
    return RoverService(
        route_map, link,
        camera=SyntheticCamera(), detector=NoopDetector(),
        publisher=ConsolePublisher(stream=events),
        config=ServiceConfig(device_id=DEVICE, secret=SECRET,
                             evidence_dir=str(tmp_path / "evidence")),
        clock=clock,
        inspector=make_hw_inspector(registry, clock, scenarios, transport),
        inspection_registry=registry,
    )


def inspect_mission(clock, mission_id="hw-m1", command_id="hw-c1",
                    waypoint="wp-b", zone="zone-a", **fields):
    return signed(MissionType.INSPECT_ZONE, mission_id, command_id, clock,
                  zone_id=zone, waypoint_id=waypoint, **fields)


def ctx_for(mission_id="hw-m1", command_id="hw-c1", **kw):
    base = {
        "mission_id": mission_id, "command_id": command_id,
        "incident_id": kw.pop("incident_id", "inc-hw"),
        "device_id": DEVICE, "zone_id": "zone-a", "waypoint_id": "wp-b",
        "target_device_id": "pi-test-01", "pose": {},
        "started_epoch": 1_700_000_000.0,
    }
    base.update(kw)
    return base


def target_for(registry, device_id="pi-test-01"):
    return registry.target(device_id)


# ---------------------------------------------------------------------------
# Command shape + registry allowlist
# ---------------------------------------------------------------------------

def test_command_shape_exact_and_mission_id_preserved():
    cmd = build_cabinet_command("inspection-001", "rack-02")
    assert cmd == {
        "mission_id": "inspection-001",
        "action": "inspect_cabinet",
        "cabinet_id": "rack-02",
    }
    # no marker/sticker/tag fields — recognition stays sticker-agnostic
    assert set(cmd) == {"mission_id", "action", "cabinet_id"}


def test_registry_cabinet_ids_allowlist(registry):
    assert registry.cabinet_ids() == frozenset({"cab-test-01"})
    assert registry.target("pi-test-01").cabinet_id == "cab-test-01"
    assert registry.target("pi-test-02").cabinet_id == ""


def test_target_without_cabinet_id_denied(registry, clock):
    insp = make_hw_inspector(registry, clock)
    with pytest.raises(InspectionDenied, match="cabinet_id"):
        insp.inspect(target_for(registry, "pi-test-02"), ctx_for())


def test_unregistered_cabinet_denied(registry, clock):
    """A target whose cabinet_id is not in the registry allowlist is
    denied before any command reaches the transport."""
    rogue = InspectionTarget.from_dict({
        "device_id": "pi-rogue", "zone_id": "zone-a",
        "waypoint_id": "wp-b", "address": "10.9.9.99",
        "cabinet_id": "cab-not-registered",
    })
    transport = SimulatedHardwareTransport(clock=clock)
    insp = make_hw_inspector(registry, clock, transport=transport)
    with pytest.raises(InspectionDenied, match="not allowlisted"):
        insp.inspect(rogue, ctx_for())
    assert transport.sent == []  # nothing was sent


# ---------------------------------------------------------------------------
# Simulated transport -> normalized report
# ---------------------------------------------------------------------------

def test_simulated_inspection_success(registry, clock):
    transport = SimulatedHardwareTransport(clock=clock)
    insp = make_hw_inspector(registry, clock, transport=transport)
    report = insp.inspect(target_for(registry), ctx_for())

    # command sent to "autonomy"
    assert transport.sent == [{
        "mission_id": "hw-m1",
        "action": ACTION_INSPECT_CABINET,
        "cabinet_id": "cab-test-01",
    }]

    assert report.status == "ok"
    assert report.mission_id == "hw-m1"
    assert report.cabinet_id == "cab-test-01"
    assert report.target_device_id == "pi-test-01"
    assert report.incident_id == "inc-hw"
    assert report.adapter == "hardware"
    assert report.provenance == "DEMO"
    assert report.synthetic is True
    assert report.started_at and report.completed_at
    assert len(report.checks) == len(SimulatedHardwareTransport.DEFAULT_CHECKS)
    assert all(c["ok"] for c in report.checks)
    assert len(report.evidence_refs) == 2
    assert all(r["ref"].startswith("cabinet://") for r in report.evidence_refs)
    assert all(len(r["sha256"]) == 64 for r in report.evidence_refs)
    assert report.evidence_refs[0]["kind"] == "cabinet_still"


def test_unreachable_cabinet(registry, clock):
    transport = SimulatedHardwareTransport(
        scenarios={"cab-test-01": {"status": "unreachable"}}, clock=clock)
    insp = make_hw_inspector(registry, clock, transport=transport)
    report = insp.inspect(target_for(registry), ctx_for())
    assert report.status == "unreachable"
    assert report.cabinet_id == "cab-test-01"
    assert report.mission_id == "hw-m1"


def test_transport_timeout_is_unreachable(registry, clock):
    transport = SimulatedHardwareTransport(
        scenarios={"cab-test-01": {"timeout": True}}, clock=clock)
    insp = make_hw_inspector(registry, clock, transport=transport)
    report = insp.inspect(target_for(registry), ctx_for())
    assert report.status == "unreachable"
    assert report.status_detail == "hardware_timeout"


def test_malformed_response_mission_id_mismatch(registry, clock):
    transport = SimulatedHardwareTransport(
        scenarios={"cab-test-01": {"malformed": True}}, clock=clock)
    insp = make_hw_inspector(registry, clock, transport=transport)
    report = insp.inspect(target_for(registry), ctx_for())
    assert report.status == "error"
    assert "mission_id_mismatch" in report.status_detail


def test_response_cabinet_mismatch(registry, clock):
    class BadCabinet(SimulatedHardwareTransport):
        def send(self, command):
            resp = super().send(command)
            resp["cabinet_id"] = "cab-other"
            return resp
    insp = make_hw_inspector(registry, clock,
                             transport=BadCabinet(clock=clock))
    report = insp.inspect(target_for(registry), ctx_for())
    assert report.status == "error"
    assert "cabinet_id_mismatch" in report.status_detail


def test_unknown_status_is_error(registry, clock):
    transport = SimulatedHardwareTransport(
        scenarios={"cab-test-01": {"status": "exploded"}}, clock=clock)
    insp = make_hw_inspector(registry, clock, transport=transport)
    report = insp.inspect(target_for(registry), ctx_for())
    assert report.status == "error"
    assert "unknown_status" in report.status_detail


def test_duplicate_ack_is_not_reported_as_success(registry, clock):
    """A duplicate may still be running or failed; it is not a result."""
    transport = SimulatedHardwareTransport(
        scenarios={"cab-test-01": {"status": "duplicate"}}, clock=clock)
    insp = make_hw_inspector(registry, clock, transport=transport)
    report = insp.inspect(target_for(registry), ctx_for())
    assert report.status == "error"
    assert report.status_detail == "duplicate_result_unverified"


def test_ok_claim_with_failed_checks_downgraded(registry, clock):
    transport = SimulatedHardwareTransport(
        scenarios={"cab-test-01": {
            "checks": [
                {"name": "cabinet_present", "ok": True, "detail": "seen",
                 "latency_ms": 3},
                {"name": "pi_heartbeat", "ok": False,
                 "detail": "timeout", "latency_ms": 900},
            ],
        }}, clock=clock)
    insp = make_hw_inspector(registry, clock, transport=transport)
    report = insp.inspect(target_for(registry), ctx_for())
    assert report.status == "degraded"  # never upgraded past evidence


def test_stale_hardware_result_flagged(registry, clock):
    transport = SimulatedHardwareTransport(
        scenarios={"cab-test-01": {"age_s": 9999}}, clock=clock)
    insp = make_hw_inspector(registry, clock, transport=transport)
    report = insp.inspect(target_for(registry), ctx_for())
    assert report.is_stale(clock() + 1, max_age_s=300.0)


def test_transport_exception_is_error_report(registry, clock):
    class Boom(SimulatedHardwareTransport):
        def send(self, command):
            raise RuntimeError("link reset")
    insp = make_hw_inspector(registry, clock, transport=Boom(clock=clock))
    report = insp.inspect(target_for(registry), ctx_for())
    assert report.status == "error"
    assert "transport_error" in report.status_detail


def test_unconfigured_transport_denies(registry, clock):
    insp = make_hw_inspector(
        registry, clock, transport=UnconfiguredHardwareTransport())
    with pytest.raises(InspectionDenied):
        insp.inspect(target_for(registry), ctx_for())


def test_evidence_refs_sanitized(registry, clock):
    transport = SimulatedHardwareTransport(
        scenarios={"cab-test-01": {
            "evidence": [
                {"kind": "photo", "ref": "cabinet://c1/x.jpg",
                 "sha256": "a" * 64},
                {"kind": "bad", "ref": ""},          # dropped: no ref
                "not-a-dict",                          # dropped
                {"kind": "log", "uri": "cabinet://c1/log"},
            ],
        }}, clock=clock)
    insp = make_hw_inspector(registry, clock, transport=transport)
    report = insp.inspect(target_for(registry), ctx_for())
    assert [r["kind"] for r in report.evidence_refs] == ["photo", "log"]


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def test_inspector_from_name_hardware(registry, clock):
    insp = inspector_from_name(
        "hardware", allowed_cabinets=registry.cabinet_ids(), clock=clock)
    assert isinstance(insp, HardwareCabinetInspector)
    assert insp.provenance == "DEMO"
    assert insp.synthetic is True


def test_hardware_transport_live_is_unconfigured(clock):
    t = hardware_transport_from_name("live", clock=clock)
    assert isinstance(t, UnconfiguredHardwareTransport)
    with pytest.raises(HardwareUnavailable):
        t.send({"mission_id": "m", "action": "inspect_cabinet",
                "cabinet_id": "c"})


def test_unknown_transport_rejected(clock):
    with pytest.raises(ValueError):
        hardware_transport_from_name("carrier-pigeon", clock=clock)


# ---------------------------------------------------------------------------
# End-to-end through RoverService
# ---------------------------------------------------------------------------

def test_service_inspect_zone_via_hardware(registry, route_map, link,
                                           clock, tmp_path):
    svc = make_service(route_map, link, clock, tmp_path, registry,
                       scenarios={})
    ok, reason, rec = svc.submit(inspect_mission(
        clock, mission_id="hw-e2e-1", incident_id="inc-e2e"))
    assert ok, reason
    run_until_done(svc, link, clock)
    final = svc.missions[-1]
    assert final.state == MissionState.COMPLETED, final.reason
    assert final.reason == "inspection_ok"

    assert len(svc.inspection_reports) == 1
    report = svc.inspection_reports[0]
    assert report.adapter == "hardware"
    assert report.cabinet_id == "cab-test-01"
    assert report.target_device_id == "pi-test-01"
    assert report.mission_id == "hw-e2e-1"
    assert report.incident_id == "inc-e2e"
    assert report.provenance == "DEMO"
    assert report.synthetic is True
    assert report.evidence_refs

    # hashed artifact contains cabinet_id + evidence_refs
    artifacts = [p for p in Path(tmp_path / "evidence").rglob("insp-hw-*.json")
                 if not p.name.endswith(".meta.json")]
    assert len(artifacts) == 1
    body = json.loads(artifacts[0].read_text())
    assert body["cabinet_id"] == "cab-test-01"
    assert body["mission_id"] == "hw-e2e-1"
    assert body["evidence_refs"]
    meta = json.loads(artifacts[0].with_name(
        artifacts[0].name[:-5] + ".meta.json").read_text())
    assert meta["cabinet_id"] == "cab-test-01"
    assert meta["sha256"] == hashlib.sha256(
        artifacts[0].read_bytes()).hexdigest()

    # telemetry carried cabinet_id for downstream correlation
    events = [json.loads(l) for l in
              (tmp_path / "events.jsonl").read_text().splitlines() if l]
    done = [e for e in events if e.get("event") == "inspection_completed"]
    assert done and done[0]["cabinet_id"] == "cab-test-01"
    assert done[0]["incident_id"] == "inc-e2e"


def test_service_unreachable_cabinet_completes_with_evidence(
        registry, route_map, link, clock, tmp_path):
    svc = make_service(
        route_map, link, clock, tmp_path, registry,
        scenarios={"cab-test-01": {"status": "unreachable"}})
    ok, reason, _ = svc.submit(inspect_mission(clock))
    assert ok, reason
    run_until_done(svc, link, clock)
    final = svc.missions[-1]
    assert final.state == MissionState.COMPLETED
    assert final.reason == "inspection_unreachable"
    report = svc.inspection_reports[0]
    assert report.status == "unreachable"
    assert report.cabinet_id == "cab-test-01"


def test_service_target_without_cabinet_denied(
        registry, route_map, link, clock, tmp_path):
    """wp-far/pi-test-02 has no cabinet_id -> denied report, mission still
    completes honestly (inspection outcome is evidence, not a crash)."""
    svc = make_service(route_map, link, clock, tmp_path, registry)
    ok, reason, _ = svc.submit(inspect_mission(
        clock, waypoint="wp-far", zone="zone-b"))
    assert ok, reason
    run_until_done(svc, link, clock)
    final = svc.missions[-1]
    assert final.state == MissionState.COMPLETED
    assert final.reason == "inspection_denied"
    report = svc.inspection_reports[0]
    assert report.status == "denied"
    assert "cabinet_id" in report.status_detail


def test_duplicate_mission_still_rejected_with_hw_inspector(
        registry, route_map, link, clock, tmp_path):
    svc = make_service(route_map, link, clock, tmp_path, registry)
    m = inspect_mission(clock, mission_id="hw-dup", command_id="hw-dup-c")
    ok1, _, _ = svc.submit(m)
    ok2, reason2, _ = svc.submit(m)
    assert ok1 and not ok2
    assert "duplicate" in reason2
