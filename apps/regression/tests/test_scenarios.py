import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from regression import (  # noqa: E402
    interception_scenario,
    mitigation_scenario,
    negative_checks,
    prevention_scenario,
)


def test_prevention_scenario_end_to_end():
    res = prevention_scenario()
    assert res["ok"], res.get("stage")
    stages = [e["stage"] for e in res["evidence"]]
    assert stages == ["posture", "candidate", "propose", "approve",
                      "execute"]


def test_interception_scenario_end_to_end():
    res = interception_scenario()
    assert res["ok"]
    outcomes = {e["action"] for e in res["evidence"]}
    assert {"redirect", "block", "allow"} <= outcomes or len(res["evidence"]) >= 3


def test_mitigation_scenario_end_to_end():
    res = mitigation_scenario()
    assert res["ok"], res["evidence"]
    rec = res["evidence"][0]["record"]
    assert rec["state"] == "verified"
    assert res["evidence"][1]["reachable"] is True


def test_negative_regressions_all_pass():
    results = negative_checks()
    failed = [r["check"] for r in results if not r["pass"]]
    assert not failed, f"regressions: {failed}"
    assert len(results) == 5
