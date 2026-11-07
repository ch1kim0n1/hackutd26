"""Mission contract validation — every rejection path, no motor commands."""

import time

from rover_mission.mission_contract import MissionValidator
from rover_mission.models import MissionType
from rover_mission.service import make_signed_mission

from conftest import DEVICE, SECRET, signed


def _validator(clock):
    return MissionValidator(device_id=DEVICE, secret=SECRET, clock=clock)


def _known():
    return {"loop-a"}, {"wp-a", "wp-b", "wp-c", "wp-home", "wp-far"}, \
        {"zone-a", "zone-b"}, {"cam-mast"}


def test_valid_patrol(clock):
    m = signed(MissionType.PATROL_ROUTE, "m1", "c1", clock, route_id="loop-a")
    res = _validator(clock).validate(m, *_known())
    assert res.ok and res.reason == ""


def test_valid_inspect(clock):
    m = signed(MissionType.INSPECT_ZONE, "m2", "c2", clock,
               zone_id="zone-a", waypoint_id="wp-b")
    res = _validator(clock).validate(m, *_known())
    assert res.ok


def test_rejects_wrong_device(clock):
    m = signed(MissionType.STOP, "m3", "c3", clock)
    m["device_id"] = "rover-99"
    # re-sign so signature is valid but device is wrong
    from rover_mission.auth import sign_mission
    m["signature"] = sign_mission(m, SECRET)
    res = _validator(clock).validate(m, *_known())
    assert not res.ok and res.reason == "wrong_device"


def test_rejects_expired(clock):
    m = signed(MissionType.STOP, "m4", "c4", clock, expires_s=-10)
    res = _validator(clock).validate(m, *_known())
    assert not res.ok and res.reason == "expired"


def test_rejects_overspeed(clock):
    m = signed(MissionType.STOP, "m5", "c5", clock, max_speed_mps=0.5)
    res = _validator(clock).validate(m, *_known())
    assert not res.ok and res.reason == "speed_cap"


def test_rejects_unknown_waypoint(clock):
    m = signed(MissionType.INSPECT_ZONE, "m6", "c6", clock,
               zone_id="zone-a", waypoint_id="wp-evil")
    res = _validator(clock).validate(m, *_known())
    assert not res.ok and res.reason == "unknown_waypoint"


def test_rejects_missing_fields(clock):
    m = signed(MissionType.INSPECT_ZONE, "m7", "c7", clock, zone_id="zone-a")
    res = _validator(clock).validate(m, *_known())
    assert not res.ok and res.reason == "missing_waypoint_id"


def test_rejects_forged_signature(clock):
    m = signed(MissionType.STOP, "m8", "c8", clock)
    m["signature"] = "0" * 64
    res = _validator(clock).validate(m, *_known())
    assert not res.ok and res.reason == "unauthorized"


def test_rejects_tampered_payload(clock):
    m = signed(MissionType.PATROL_ROUTE, "m9", "c9", clock, route_id="loop-a")
    m["type"] = "return_home"  # tamper after signing
    res = _validator(clock).validate(m, *_known())
    assert not res.ok and res.reason == "unauthorized"


def test_rejects_bad_schema(clock):
    m = signed(MissionType.STOP, "m10", "c10", clock)
    m["schema_version"] = 2
    from rover_mission.auth import sign_mission
    m["signature"] = sign_mission(m, SECRET)
    res = _validator(clock).validate(m, *_known())
    assert not res.ok and res.reason == "bad_schema_version"


def test_rejects_unknown_type(clock):
    m = signed(MissionType.STOP, "m11", "c11", clock)
    m["type"] = "self_destruct"
    from rover_mission.auth import sign_mission
    m["signature"] = sign_mission(m, SECRET)
    res = _validator(clock).validate(m, *_known())
    assert not res.ok and res.reason == "unknown_type"
