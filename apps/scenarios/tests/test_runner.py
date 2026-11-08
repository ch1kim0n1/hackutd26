import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # apps/scenarios
sys.path.insert(0, str(ROOT / "src"))

from scenarios import SCENARIOS, run_all  # noqa: E402


def test_all_three_scenarios_pass():
    results = run_all()
    assert len(results) == 3
    for r in results:
        assert r["ok"], r
        assert r["label"] == "MOCK"


def test_trace_completeness():
    """Every claim traceable to evidence; every evidence id in steps."""
    for name in SCENARIOS:
        trace = json.loads(
            (ROOT / "artifacts" / name / "trace.json").read_text())
        assert trace["schema"] == "scenario-trace/1"
        assert trace["label"] in ("MOCK", "LIVE")
        step_ids = {s["evidence_id"] for s in trace["steps"]}
        for claim in trace["claims"]:
            assert claim["evidence_ids"], "claim without evidence"
            assert set(claim["evidence_ids"]) <= step_ids | {"ev-none"}
        assert trace["uncertainty"]
        assert trace["agent_summary"]


def test_incident_records_persisted():
    for name in SCENARIOS:
        rec = json.loads(
            (ROOT / "artifacts" / name / "incident_record.json")
            .read_text())
        assert rec["schema"] == "incident-record/1"
        assert rec["evidence_ids"]
        assert rec["timeline"]
        assert rec["status"] in ("resolved", "failed")
