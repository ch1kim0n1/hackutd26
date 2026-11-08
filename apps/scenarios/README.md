# apps/scenarios — autonomous investigation scenarios (#114)

`python -m scenarios.runner` (PYTHONPATH=src:../regression/src:
../agent/nemotron_client/src) runs prevention / interception /
mitigation end-to-end via apps/regression, attaches a Nemotron summary
(FakeNemotronModel = MOCK label; set NEMOTRON_* env for live), and
writes artifacts/<scenario>/{trace.json,incident_record.json}.

Trace contract: scenario-trace/1 — every claim cites evidence_ids
produced by steps; MOCK|LIVE label; uncertainty always present.
Dashboard consumes via src/command/recordedTrace.ts (RECORDED_TRACES +
assertTraceComplete, vitest-covered).

Artifacts committed under artifacts/ are regenerated each run.
