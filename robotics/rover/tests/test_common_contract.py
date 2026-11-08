"""sentinel.rover.* v1 contract tests — issue #115.

Fixture-driven: contracts/rover/fixtures/*.json is the shared cross-language
contract consumed identically by autonomy/tests and mission-shim/test.
"""
import json
from pathlib import Path

import pytest
from conftest import run_until_done, signed

from rover_mission import common
from rover_mission.auth import verify_mission_signature
from rover_mission.common import (
    module_report_fields, validate_common_evidence, validate_common_mission,
    validate_common_telemetry,
)

SECRET = b"contract-test-secret"
DEVICE = "rover-01"
FIXTURES = Path(__file__).resolve().parents[3] / "contracts" / "rover" / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text())


MISSIONS = load("missions.json")
TELEMETRY = load("telemetry.json")
EVIDENCE = load("evidence.json")


def unsigned(m):
    return {k: v for k, v in m.items() if k != "signature"}


# ---------------------------------------------------------------------------
# Mission round-trips
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", MISSIONS, ids=[c["name"] for c in MISSIONS])
def test_common_mission_validates(case):
    ok, reason = validate_common_mission(case["common"])
    assert ok, reason


@pytest.mark.parametrize("case", MISSIONS, ids=[c["name"] for c in MISSIONS])
def test_common_to_module_command(case):
    got = common.common_to_module_command(case["common"])
    assert got == case["module_command"], case["name"]


@pytest.mark.parametrize("case", MISSIONS, ids=[c["name"] for c in MISSIONS])
def test_module_command_round_trip(case):
    if case["module_command"] is None:
        pytest.skip("not module-dispatchable")
    back = common.module_command_to_common(case["module_command"])
    # commandJson carries no issued_at (producer metadata) and no
    # route_id/camera_id (shim resolution details) — docs/14 §3.
    # Everything else round-trips.
    expected = {k: v for k, v in case["common"].items()
                if k not in ("issued_at", "route_id", "camera_id")}
    assert back == expected, case["name"]
    for dropped in ("issued_at", "route_id", "camera_id"):
        assert dropped not in back
    # and forward again is a fixed point
    assert common.common_to_module_command(back) == case["module_command"]


@pytest.mark.parametrize("case", MISSIONS, ids=[c["name"] for c in MISSIONS])
def test_common_to_signed_rover_mission(case):
    shim = case["shim"]
    got = common.common_to_rover_mission(
        case["common"], device_id=DEVICE, secret=SECRET,
        routes=shim.get("routes"), camera_id=shim.get("camera_id", "cam-mast"))
    assert got is not None, case["name"]
    assert unsigned(got) == case["rover_mission"], case["name"]
    # HMAC preserved: signature verifies exactly like mission_contract.py
    assert verify_mission_signature(got, SECRET)
    assert not verify_mission_signature(got, b"wrong-secret")


@pytest.mark.parametrize("case", MISSIONS, ids=[c["name"] for c in MISSIONS])
def test_rover_round_trip_fixed_point(case):
    """common -> rover -> common -> rover. Fixed-point only where the rover
    form preserves the module-required fields (inspect_zone, patrol,
    wireless_rescan). capture_photo/return_home/hold are marked
    rover_form_lossy: the rover object drops zone_id/waypoint_id, so the
    rover-derived common is no longer module-dispatchable and the second leg
    correctly refuses — the module path remains the only authority for them."""
    shim = case["shim"]
    rover1 = common.common_to_rover_mission(
        case["common"], device_id=DEVICE, secret=SECRET,
        routes=shim.get("routes"), camera_id=shim.get("camera_id", "cam-mast"))
    assert rover1 is not None
    common2 = common.rover_mission_to_common(rover1)
    assert common2 is not None
    rover2 = common.common_to_rover_mission(
        common2, device_id=DEVICE, secret=SECRET,
        routes=shim.get("routes"), camera_id=shim.get("camera_id", "cam-mast"))
    if case.get("rover_form_lossy"):
        assert rover2 is None, case["name"]
    else:
        assert rover2 is not None
        assert unsigned(rover1) == unsigned(rover2), case["name"]


def test_patrol_selector_resolves_to_route():
    """patrol waypoint_id is a selector; route_id is the resolved authority."""
    case = next(c for c in MISSIONS if c["name"] == "patrol-waypoint-selector")
    common2 = common.rover_mission_to_common(
        {**case["rover_mission"], "signature": "x" * 64})
    assert common2["type"] == "patrol"
    assert common2["route_id"] == "patrol-rack"
    # waypoint_id is not carried on the rover patrol_route form — documented
    assert "waypoint_id" not in common2


def test_wireless_rescan_not_module_dispatchable():
    case = next(c for c in MISSIONS if c["name"] == "wireless-rescan")
    assert common.common_to_module_command(case["common"]) is None
    # but the rover leg works and round-trips
    rover = common.common_to_rover_mission(
        case["common"], device_id=DEVICE, secret=SECRET,
        routes=case["shim"]["routes"])
    assert rover is not None and rover["type"] == "wireless_rescan"
    back = common.rover_mission_to_common(rover)
    assert back["type"] == "wireless_rescan"
    assert back["zone_id"] == "rack-01"


# ---------------------------------------------------------------------------
# Validation negatives
# ---------------------------------------------------------------------------

def _valid():
    return dict(MISSIONS[0]["common"])


@pytest.mark.parametrize("mutate,reason", [
    (lambda m: m.update(contract="bogus"), "bad_contract"),
    (lambda m: m.update(schema_version=2), "bad_schema_version"),
    (lambda m: m.pop("mission_id"), "missing_mission_id"),
    (lambda m: m.update(type="launch_missiles"), "unknown_type"),
    (lambda m: m.update(type="inspect_zone", waypoint_id=""), "missing_waypoint_id"),
    (lambda m: m.update(type="patrol", waypoint_id=None, route_id=None), "missing_waypoint_id|route_id"),
    (lambda m: m.update(type="wireless_rescan", zone_id=None), "missing_zone_id"),
    (lambda m: m.update(expires_at="not-a-date"), "bad_expires_at"),
    (lambda m: m.pop("expires_at"), "missing_expires_at"),
    (lambda m: m.update(max_speed_mps=-1), "bad_max_speed_mps"),
    (lambda m: m.update(zone_id="zöne"), "non-ascii field zone_id"),
])
def test_common_mission_rejects(mutate, reason):
    m = _valid()
    mutate(m)
    ok, got = validate_common_mission(m)
    assert not ok
    assert got == reason


def test_module_leg_enforces_module_window():
    m = _valid()
    m["max_speed_mps"] = 0.9  # outside module (0.05, 0.5]
    assert validate_common_mission(m)[0]           # common level: fine
    assert common.common_to_module_command(m) is None  # module leg: rejected
    m["max_speed_mps"] = 0.5
    assert common.common_to_module_command(m) is not None


def test_module_leg_requires_zone_waypoint():
    m = _valid()
    m["type"] = "return_home"
    m.pop("zone_id"); m.pop("waypoint_id")
    assert validate_common_mission(m)[0]            # common allows it
    assert common.common_to_module_command(m) is None  # module does not


# ---------------------------------------------------------------------------
# State reconciliation (docs/14 §4)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("state,expected", [
    ("accepted", {"state": "accepted", "reason": "accepted"}),
    ("navigating", {"state": "navigating", "reason": "navigating"}),
    ("scanning", {"state": "navigating", "reason": "scanning"}),
    ("completed", {"state": "completed", "reason": "completed"}),
    ("failed", {"state": "failed", "reason": "failed"}),
    ("aborted", {"state": "failed", "reason": "aborted"}),
    ("timed_out", {"state": "failed", "reason": "timed_out"}),
    ("queued", None),
    ("proposed", None),
    ("approved", None),
    ("dispatched", None),
    ("expired", None),
    ("cancelled", None),
])
def test_module_report_fields(state, expected):
    assert module_report_fields(state) == expected


def test_module_report_fields_preserves_native_reason():
    got = module_report_fields("aborted", "estop_asserted")
    assert got == {"state": "failed", "reason": "aborted:estop_asserted"}
    got = module_report_fields("timed_out", "waypoint_timeout")
    assert got == {"state": "failed", "reason": "timed_out:waypoint_timeout"}


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", [c for c in TELEMETRY if "rover_event" in c],
                         ids=[c["name"] for c in TELEMETRY if "rover_event" in c])
def test_rover_event_to_common(case):
    got = common.rover_event_to_common(case["rover_event"],
                                       provenance=case["provenance"])
    assert got == case["common"], case["name"]
    assert validate_common_telemetry(got)[0]


def test_autonomy_report_to_common():
    case = next(c for c in TELEMETRY if c["name"] == "autonomy-pose-patrol")
    got = common.autonomy_report_to_common(
        case["autonomy_report"], device_id=case["device_id"],
        provenance=case["provenance"], observed_at=case["observed_at"])
    assert got == case["common"]
    assert validate_common_telemetry(got)[0]


def test_telemetry_rejects_bad_state_and_provenance():
    base = dict(TELEMETRY[0]["common"])
    bad = dict(base, state="exploded")
    assert validate_common_telemetry(bad)[0] is False
    bad = dict(base, provenance="SIM")   # SIM is not in the frozen vocabulary
    assert validate_common_telemetry(bad) == (False, "bad_provenance")
    bad = dict(base, pose={"x": 1, "y": 2})  # missing heading/unit/frame
    assert validate_common_telemetry(bad) == (False, "bad_pose")


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", EVIDENCE, ids=[c["name"] for c in EVIDENCE])
def test_evidence_to_common(case):
    got = common.evidence_to_common(case["evidence"], device_id=case["device_id"])
    assert got == case["common"], case["name"]
    if case["common"] is not None:
        assert validate_common_evidence(got)[0]


def test_evidence_module_row():
    case = EVIDENCE[0]
    got = common.common_to_module_evidence_row(
        case["common"], incident_id=case["module_row"]["incident_id"],
        trust_tier=case["module_row"]["trust_tier"],
        trace_id=case["module_row"]["trace_id"])
    assert got == case["module_row"]["expected"]


def test_synthetic_evidence_is_demo_provenance():
    case = next(c for c in EVIDENCE if c["name"] != "rover-photo-sidecar")
    if case["common"] is None:
        pytest.skip("rejection case")
    assert case["common"]["provenance"] == "DEMO"


# ---------------------------------------------------------------------------
# Live-stack integration: real RoverService sim output must validate
# ---------------------------------------------------------------------------

def test_service_telemetry_and_evidence_validate(service, link, clock,
                                                tmp_path):
    """Run a real patrol on the simulated link; every emitted telemetry event
    and every stored evidence artifact must validate against the common
    schema — proving 'telemetry/evidence produced by each stack validates'."""
    from rover_mission.models import MissionType

    mission = signed(MissionType.PATROL_ROUTE, "mis-rt-1", "cmd-rt-1", clock,
                     route_id="loop-a")
    ok, reason, _ = service.submit(mission)
    assert ok, reason
    run_until_done(service, link, clock)

    events = [json.loads(l) for l in
              (tmp_path / "events.jsonl").read_text().splitlines() if l.strip()]
    assert len(events) >= 3
    states = []
    for ev in events:
        common_ev = common.rover_event_to_common(ev, provenance="DEMO")
        assert common_ev is not None, ev
        assert validate_common_telemetry(common_ev)[0]
        assert common_ev["mission_id"] == "mis-rt-1"
        if common_ev.get("state"):
            states.append(common_ev["state"])
    assert "completed" in states

    # evidence artifacts written by the service validate as common evidence
    metas = list(Path(service.cfg.evidence_dir).rglob("ev-*.json"))
    assert metas, "expected photo evidence from patrol waypoint wp-b"
    for meta_path in metas:
        meta = json.loads(meta_path.read_text())
        ev_common = common.evidence_to_common(meta, device_id=DEVICE)
        assert ev_common is not None, meta_path
        assert validate_common_evidence(ev_common)[0]
        assert ev_common["synthetic"] is True   # SyntheticCamera -> DEMO
        assert ev_common["provenance"] == "DEMO"
