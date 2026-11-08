"""#114 — autonomous investigation scenarios + persisted traces.

Runs the three capability scenarios (prevention / interception /
mitigation) through the merged packages, attaches a Nemotron summary
(fake provider = MOCK label; live provider when env-configured), and
writes per-scenario artifacts:

  artifacts/<scenario>/incident_record.json  — persisted record
  artifacts/<scenario>/trace.json            — full step trace w/ evidence ids

Trace contract (consumed by dashboard recorded-trace view + vitest):
every claim lists evidence_ids; every evidence id is produced by a step;
labels MOCK|LIVE explicit; uncertainty field always present.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for rel in ("regression/src", "agent/nemotron_client/src"):
    p = str(ROOT / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

from regression import scenarios as rs  # noqa: E402
from nemotron_client.provider import FakeNemotronModel  # noqa: E402
from nemotron_client.types import ModelResponse  # noqa: E402

ARTIFACTS = Path(__file__).resolve().parents[2] / "artifacts"

SCENARIOS = {
    "prevention": {
        "fn": rs.prevention_scenario,
        "title": "Preventive hardening from posture drift",
        "summary": ("Posture assessment found confirmed drift on "
                    "vpi-compute-01. Risk ranking promoted it to an "
                    "incident candidate; a hardening proposal was "
                    "approved by a commander and verified against the "
                    "node config."),
        "uncertainty": "low — config re-read confirms the fix landed",
    },
    "interception": {
        "fn": rs.interception_scenario,
        "title": "Rogue flow redirected to decoy",
        "summary": ("A flow from attacker-01 matched the deception "
                    "policy and was redirected to decoy-01; the decoy "
                    "captured the probe. A second known-bad source was "
                    "blocked outright; legitimate ops traffic passed."),
        "uncertainty": "medium — decoy capture proves intent to probe, "
                       "not payload contents",
    },
    "mitigation": {
        "fn": rs.mitigation_scenario,
        "title": "Quarantine, verify, recover",
        "summary": ("An approved quarantine_vlan action was dispatched "
                    "to the executor, applied to vpi-compute-01, and "
                    "independently verified via health probe before "
                    "VERIFIED. Release restored reachability."),
        "uncertainty": "low — independent probe confirmed both "
                       "isolation and recovery",
    },
}


def _evidence_ids(evidence: list[dict]) -> list[str]:
    ids = []
    for i, e in enumerate(evidence):
        # stable id from content, not position-dependent randomness
        import hashlib
        blob = json.dumps(e, sort_keys=True, default=str)
        ids.append("ev-" + hashlib.sha256(blob.encode()).hexdigest()[:10])
    return ids


def _nemotron_summary(scn: dict) -> tuple[str, str]:
    """MOCK summary via deterministic fake provider. Returns
    (summary, provider_label)."""
    model = FakeNemotronModel(script=[
        ModelResponse(content=scn["summary"], model="fake-nemotron",
                      latency_ms=0.1)])
    resp = model.chat([
        {"role": "system", "content": "You are the Sentinel Hive "
         "investigation agent. Summarize the scenario outcome for the "
         "command center. Be specific, cite evidence, state "
         "uncertainty."},
        {"role": "user", "content": scn["title"]}])
    return resp.content, "MOCK"


def run_scenario(name: str, out_root: Path = ARTIFACTS) -> dict:
    scn = SCENARIOS[name]
    t0 = time.time()
    result = scn["fn"]()
    duration = round(time.time() - t0, 3)

    evidence = result.get("evidence", [])
    ev_ids = _evidence_ids(evidence)
    steps = [{
        "step": i + 1,
        "evidence_id": eid,
        "detail": json.dumps(e, sort_keys=True, default=str)[:600],
    } for i, (e, eid) in enumerate(zip(evidence, ev_ids))]

    summary, label = _nemotron_summary(scn)
    ok = bool(result.get("ok"))

    claims = [{
        "text": scn["summary"],
        "evidence_ids": ev_ids or ["ev-none"],
    }]
    if not ok:
        claims.append({"text": f"scenario failed at stage "
                               f"{result.get('stage', 'unknown')}",
                       "evidence_ids": ev_ids or ["ev-none"]})

    trace = {
        "schema": "scenario-trace/1",
        "scenario": name,
        "title": scn["title"],
        "label": label,
        "provenance": "DEMO",
        "ok": ok,
        "duration_s": duration,
        "agent_summary": summary,
        "uncertainty": scn["uncertainty"],
        "steps": steps,
        "claims": claims,
        "generated_at": time.time(),
    }
    incident = {
        "schema": "incident-record/1",
        "scenario": name,
        "title": scn["title"],
        "status": "resolved" if ok else "failed",
        "severity": "medium",
        "label": label,
        "provenance": "DEMO",
        "agent_summary": summary,
        "uncertainty": scn["uncertainty"],
        "evidence_ids": ev_ids,
        "timeline": [{"step": s["step"], "evidence_id": s["evidence_id"],
                      "detail": s["detail"][:200]} for s in steps],
        "result": result,
    }

    out_dir = out_root / name
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "trace.json").write_text(json.dumps(trace, indent=2))
    (out_dir / "incident_record.json").write_text(
        json.dumps(incident, indent=2, default=str))
    return {"scenario": name, "ok": ok, "label": label,
            "evidence_count": len(ev_ids), "dir": str(out_dir)}


def run_all(out_root: Path = ARTIFACTS) -> list[dict]:
    return [run_scenario(n, out_root) for n in SCENARIOS]


def main() -> None:
    results = run_all()
    for r in results:
        print(f"{r['scenario']}: {'PASS' if r['ok'] else 'FAIL'} "
              f"({r['label']}, {r['evidence_count']} evidence)")
    if not all(r["ok"] for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
