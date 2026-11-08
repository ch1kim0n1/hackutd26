import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "posture" / "src"))

from risk_priority import prioritize, score_finding
from posture import PostureEngine, seed_weak_fixture


def posture_findings():
    return PostureEngine(seed_weak_fixture()).assess()


def test_empty_input():
    assert prioritize([]) == []


def test_ranking_order():
    ranked = prioritize(posture_findings())
    assert ranked, "expected ranked findings"
    scores = [r["score"] for r in ranked]
    assert scores == sorted(scores, reverse=True)
    assert [r["rank"] for r in ranked] == list(range(1, len(ranked) + 1))


def test_top_item_is_critical_or_high():
    ranked = prioritize(posture_findings())
    assert ranked[0]["severity"] in ("critical", "high")
    # compute node criticality boosts it
    assert "criticality" in ranked[0]["explanation"]


def test_dedup_repeat_findings():
    f = posture_findings()[0]
    dup = dict(f)
    once = prioritize([f])
    twice = prioritize([f, dup, dict(f)])
    assert len(once) == len(twice) == 1


def test_dedup_keeps_higher_confidence():
    base = {"check_id": "c", "node_ref": "n1", "severity": "high",
            "confidence": "suspected", "provenance": "DEMO",
            "summary": "s", "evidence_refs": [], "detail": {}}
    better = dict(base, confidence="confirmed")
    ranked = prioritize([base, better])
    assert len(ranked) == 1
    assert ranked[0]["confidence"] == "confirmed"


def test_score_formula_documented():
    f = {"severity": "high", "confidence": "confirmed",
         "node_ref": "vpi-compute-01", "check_id": "x", "detail": {},
         "provenance": "DEMO", "summary": "", "evidence_refs": []}
    score, expl = score_finding(f)
    # high(5.0) * confirmed(1.0) * exposure(1.5 rack-01 via node?) * crit(1.5)
    # node_ref vpi-compute-01 -> criticality 1.5; exposure default 1.0
    assert abs(score - 7.5) < 0.01
    assert "severity=high" in expl and "confidence=confirmed" in expl


def test_output_contract_fields():
    for r in prioritize(posture_findings()):
        assert set(r) == {"rank", "finding_id", "node_ref", "check_id",
                          "severity", "confidence", "score",
                          "explanation", "provenance", "evidence_refs"}
        assert isinstance(r["score"], float)
        assert r["finding_id"]


def test_deterministic():
    a = prioritize(posture_findings())
    b = prioritize(posture_findings())
    assert a == b


def test_unknown_confidence_scores_low():
    confirmed = {"severity": "high", "confidence": "confirmed",
                 "node_ref": "vpi-compute-01", "check_id": "x",
                 "detail": {}, "provenance": "DEMO", "summary": "",
                 "evidence_refs": []}
    unknown = dict(confirmed, confidence="unknown", check_id="y")
    rs = {r["confidence"]: r["score"] for r in prioritize([confirmed, unknown])}
    assert rs["confirmed"] > rs["unknown"]
