"""autonomy/mission_map tests — issue #115.

mission_map is a self-contained parity port of rover_mission/common.py (autonomy
deploys to the Pi as flat scripts and cannot import the rover package). These
tests pin its behavior against the shared contracts/rover/fixtures and verify
common -> directive -> common and report -> common round-trips.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mission_map  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[2] / "contracts" / "rover" / "fixtures"
MISSIONS = json.loads((FIXTURES / "missions.json").read_text())
TELEMETRY = json.loads((FIXTURES / "telemetry.json").read_text())


def load(name):
    return json.loads((FIXTURES / name).read_text())


@pytest.mark.parametrize("case", MISSIONS, ids=[c["name"] for c in MISSIONS])
def test_common_to_directive(case):
    got = mission_map.common_to_directive(
        case["common"], now=case["now"],
        waypoint_table=case.get("waypoint_table") or {})
    assert got == case["autonomy_directive"], case["name"]


@pytest.mark.parametrize("case", MISSIONS, ids=[c["name"] for c in MISSIONS])
def test_directive_to_common_round_trip(case):
    directive = mission_map.common_to_directive(
        case["common"], now=case["now"],
        waypoint_table=case.get("waypoint_table") or {})
    assert directive is not None
    back = mission_map.directive_to_common(directive)
    assert back is not None, case["name"]
    ok, reason = mission_map.validate_common_mission(back)
    assert ok, reason
    # semantic equality on every field the directive preserves; camera_id is
    # shim-resolution detail autonomy never sees (docs/14 §3)
    for k, v in case["common"].items():
        if k == "camera_id":
            continue
        assert back.get(k) == v, (case["name"], k, v, back.get(k))
    assert "camera_id" not in back


def test_autonomy_native_directive_rejected():
    """Brain-emitted modes (WALL_FOLLOW etc.) must not become common missions."""
    assert mission_map.directive_to_common(
        {"contract": "sentinel.rover.autonomy_directive",
         "schema_version": 1, "behavior": "WALL_FOLLOW"}) is None
    assert mission_map.directive_to_common({"behavior": "EXPLORE"}) is None


@pytest.mark.parametrize("case", [c for c in TELEMETRY if "autonomy_report" in c],
                         ids=[c["name"] for c in TELEMETRY if "autonomy_report" in c])
def test_report_to_common(case):
    got = mission_map.report_to_common(
        case["autonomy_report"], device_id=case["device_id"],
        provenance=case["provenance"], observed_at=case["observed_at"])
    assert got == case["common"]
    assert mission_map.validate_common_telemetry(got)[0]


def test_report_rejects_non_autonomy_payloads():
    assert mission_map.report_to_common({"foo": 1}, device_id="d") is None
    assert mission_map.report_to_common(
        {"pose": [0, 0], "mode": "PATROL"}, device_id="d") is None  # short pose
    assert mission_map.report_to_common("not-a-dict", device_id="d") is None
    # pose >= 3 elements is tolerated (first three used) — same as the TS port
    got = mission_map.report_to_common(
        {"pose": [0, 0, 0, 9], "mode": "PATROL"}, device_id="d")
    assert got is not None and got["pose"]["heading_rad"] == 0


def test_validate_parity_on_fixture_commons():
    for case in MISSIONS:
        ok, _ = mission_map.validate_common_mission(case["common"])
        assert ok, case["name"]
    for case in TELEMETRY:
        if "common" in case:
            ok, _ = mission_map.validate_common_telemetry(case["common"])
            assert ok, case["name"]
