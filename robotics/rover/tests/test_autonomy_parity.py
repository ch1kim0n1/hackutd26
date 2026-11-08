"""Cross-language parity: autonomy/mission_map.py must agree with the
canonical rover_mission/common.py on every shared-table value and on every
fixture verdict. If either side drifts, this test fails — that is the point
of the port."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "autonomy"))

from rover_mission import common as canonical  # noqa: E402
import mission_map as port  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[3] / "contracts" / "rover" / "fixtures"
MISSIONS = json.loads((FIXTURES / "missions.json").read_text())

TABLES = [
    ("SCHEMA_VERSION", "SCHEMA_VERSION"),
    ("CONTRACT_MISSION", "CONTRACT_MISSION"),
    ("CONTRACT_TELEMETRY", "CONTRACT_TELEMETRY"),
    ("PROVENANCE_VALUES", "PROVENANCE_VALUES"),
    ("COMMON_MISSION_TYPES", "COMMON_MISSION_TYPES"),
    ("MODULE_MISSION_TYPES", "MODULE_MISSION_TYPES"),
    ("TYPE_TO_ROVER", "TYPE_TO_ROVER"),
    ("TYPE_FROM_ROVER", "TYPE_FROM_ROVER"),
    ("MISSION_REQUIRED_FIELDS", "MISSION_REQUIRED_FIELDS"),
    ("MISSION_ANY_OF_FIELDS", "MISSION_ANY_OF_FIELDS"),
    ("MODULE_REQUIRED_FIELDS", "MODULE_REQUIRED_FIELDS"),
    ("MODULE_SPEED_MIN_EXCLUSIVE", "MODULE_SPEED_MIN_EXCLUSIVE"),
    ("MODULE_SPEED_MAX", "MODULE_SPEED_MAX"),
    ("ROVER_STATES", "ROVER_STATES"),
    ("COMMON_STATES", "COMMON_STATES"),
    ("POSE_UNITS", "POSE_UNITS"),
    ("AUTONOMY_POSE_UNIT", "AUTONOMY_POSE_UNIT"),
    ("AUTONOMY_POSE_FRAME", "AUTONOMY_POSE_FRAME"),
]


@pytest.mark.parametrize("canon_name,port_name", TABLES)
def test_mapping_tables_identical(canon_name, port_name):
    a = getattr(canonical, canon_name)
    b = getattr(port, port_name)
    assert a == b, f"{canon_name} drifted: canonical={a!r} port={b!r}"


@pytest.mark.parametrize("case", MISSIONS, ids=[c["name"] for c in MISSIONS])
def test_validators_agree_on_fixtures(case):
    assert canonical.validate_common_mission(case["common"]) == \
        port.validate_common_mission(case["common"])


def test_module_leg_is_canonical_only():
    """autonomy never emits module commandJson — the module leg lives in
    rover_mission.common + mission-shim only. mission_map must not grow one."""
    assert not hasattr(port, "common_to_module_command")
    assert not hasattr(port, "common_to_rover_mission")


def test_edge_cases_agree():
    base = dict(MISSIONS[0]["common"])
    mutants = [
        {**base, "contract": "x"},
        {**base, "type": "nope"},
        {**base, "max_speed_mps": "fast"},
        {**base, "zone_id": "zöne"},
        {**base, "expires_at": ""},
        {k: v for k, v in base.items() if k != "waypoint_id"},
    ]
    for m in mutants:
        assert canonical.validate_common_mission(m) == port.validate_common_mission(m), m
