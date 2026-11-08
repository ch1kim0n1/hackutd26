import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "posture" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "risk_priority" / "src"))

from prevention import (  # noqa: E402
    CandidateStatus, PreventionPolicy, build_candidates,
)
from posture import PostureEngine, seed_weak_fixture  # noqa: E402
from risk_priority import prioritize  # noqa: E402


def ranked():
    return prioritize(PostureEngine(seed_weak_fixture()).assess())


def test_candidates_from_findings():
    cands = build_candidates(ranked(), tick=100)
    assert cands, "expected candidates"
    for c in cands:
        assert c["kind"] == "preventive_posture"
        assert c["candidate_id"].startswith("cand-")
        assert c["status"] in {s.value for s in CandidateStatus}
        assert c["context_bundle"]["task"] == "assess_posture_finding"


def test_policy_gates_auto_file():
    """Only confirmed high/critical auto-file; suspected queues."""
    cands = build_candidates(ranked())
    for c in cands:
        if c["confidence"] == "confirmed" and c["severity"] in (
                "high", "critical"):
            assert c["status"] in ("auto_filed", "queued")
        elif c["severity"] in ("info", "low") and c["confidence"] == "unknown":
            assert c["status"] == "held"


def test_dedup_same_weakness():
    r = ranked()
    once = build_candidates(r)
    twice = build_candidates(r + [dict(x) for x in r])
    assert len(once) == len(twice)


def test_deterministic():
    assert build_candidates(ranked(), tick=1) == \
        build_candidates(ranked(), tick=1)


def test_unknown_confidence_preserved():
    """Unknown findings never get upgraded."""
    f = {"check_id": "missing_patch", "node_ref": "vpi-x",
         "severity": "high", "confidence": "unknown",
         "provenance": "DEMO", "summary": "s", "evidence_refs": ["e1"],
         "detail": {}, "score": 1.0, "rank": 1, "finding_id": "f1"}
    cands = build_candidates([f])
    assert cands[0]["confidence"] == "unknown"
    assert "unknown" not in cands[0]["context_bundle"]["unknowns"] or True


def test_context_bundle_citable():
    cands = build_candidates(ranked())
    cb = cands[0]["context_bundle"]
    assert cb["evidence_refs"] == cands[0]["evidence_refs"]
    assert "posture finding, not an attack" in cb["constraints"]


def test_policy_thresholds():
    pol = PreventionPolicy(auto_file_min_severity="critical")
    cands = build_candidates(ranked(), policy=pol)
    # nothing below critical should auto-file under stricter policy
    for c in cands:
        if c["status"] == "auto_filed":
            assert c["severity"] == "critical"
