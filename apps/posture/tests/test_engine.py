import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from posture import (
    Confidence, FixtureNode, FixtureProvider, PostureEngine, Provenance,
    Severity, seed_weak_fixture,
)


def test_seeded_weakness_found_without_attacker():
    """Planted weaknesses discovered with zero attacker events."""
    findings = PostureEngine(seed_weak_fixture()).assess()
    checks = {f["check_id"] for f in findings}
    assert "open_port_unexpected" in checks
    assert "default_credential" in checks
    assert "missing_patch" in checks
    assert "baseline_drift_new" in checks
    # all on the weak node
    weak = [f for f in findings if f["node_ref"] == "vpi-compute-01"]
    assert weak and all(f["provenance"] == "DEMO" for f in weak)


def test_finding_schema_fields():
    for f in PostureEngine(seed_weak_fixture()).assess():
        assert set(f) == {"check_id", "node_ref", "severity", "confidence",
                          "provenance", "summary", "evidence_refs", "detail"}
        assert f["severity"] in {s.value for s in Severity}
        assert f["confidence"] in {c.value for c in Confidence}
        assert f["provenance"] in {p.value for p in Provenance}
        assert isinstance(f["evidence_refs"], list)


def test_unknown_preserved_not_confirmed():
    node = FixtureNode(
        node_id="vpi-mystery",
        baseline={"expected_patch_level": "2026-10"},
        patch_level="unknown",
    )
    findings = PostureEngine(FixtureProvider([node])).assess()
    patch = [f for f in findings if f["check_id"] == "missing_patch"]
    assert patch and patch[0]["confidence"] == "unknown"
    assert patch[0]["severity"] == "medium"   # downgraded, not confirmed


def test_baseline_diff_new_vs_known():
    node = FixtureNode(
        node_id="vpi-compute-01",
        config={"ssh_password_auth": True, "fw_profile": "open"},
        baseline={"ssh_password_auth": False, "fw_profile": "restricted",
                  "accepted_drift": ["fw_profile=open"]},
    )
    findings = PostureEngine(FixtureProvider([node])).assess()
    drift = {f["detail"]["key"]: f for f in findings
             if f["check_id"].startswith("baseline_drift")}
    assert drift["ssh_password_auth"]["check_id"] == "baseline_drift_new"
    assert drift["ssh_password_auth"]["severity"] == "medium"
    assert drift["fw_profile"]["check_id"] == "baseline_drift_known"
    assert drift["fw_profile"]["severity"] == "low"


def test_deterministic_output():
    a = PostureEngine(seed_weak_fixture()).assess()
    b = PostureEngine(seed_weak_fixture()).assess()
    assert a == b
    # sorted by severity desc then node/check
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    keys = [(sev_order[f["severity"]], f["node_ref"], f["check_id"])
            for f in a]
    assert keys == sorted(keys)


def test_empty_node_yields_unknown_finding():
    node = FixtureNode(node_id="vpi-empty")
    findings = PostureEngine(FixtureProvider([node])).assess()
    assert any(f["check_id"] == "insufficient_evidence"
               and f["confidence"] == "unknown" for f in findings)


def test_expected_ports_not_flagged():
    node = FixtureNode(
        node_id="vpi-clean",
        services=({"name": "sshd", "port": 22, "protocol": "tcp"},),
        open_ports=({"port": 22, "proto": "tcp", "service_name": "sshd"},),
        config={"a": 1}, baseline={"a": 1, "expected_patch_level": "x"},
        patch_level="x",
        credentials=({"user": "u", "method": "key", "strength": "strong"},),
    )
    findings = PostureEngine(FixtureProvider([node])).assess()
    assert findings == [] or all(
        f["check_id"] == "insufficient_evidence" for f in findings)
