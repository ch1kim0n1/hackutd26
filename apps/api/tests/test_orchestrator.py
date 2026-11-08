"""Orchestrator tests (issue #112): synthetic observation -> automatic
investigation, dedup/idempotency, budget exhaustion, citation guards,
provenance, and the machine-principal HTTP ingest path."""
import json

import pytest

from sentinel_api.orchestrator import InvestigationEvent, Orchestrator
from investigator.scripted import FakeResponse, ScriptedModel, tc


def _event(**kw):
    base = dict(event_id="evt-1", kind="motion", source="observation",
                device_id="device-lab-01", zone_id="rack-01",
                summary="motion in rack-01", provenance="MOCK",
                observed_at="2026-01-01T00:00:00Z")
    base.update(kw)
    return InvestigationEvent(**base)


def test_synthetic_observation_triggers_investigation(state):
    orch = state.orchestrator
    assert orch.enqueue(_event()) == "accepted"
    runs = orch.pump()
    assert len(runs) == 1
    run = runs[0]
    assert run["status"] in {"completed", "degraded", "rejected"}
    assert run["incident_id"].startswith("inc-")
    assert run["by"] == "orchestrator"
    assert run["provenance"] == "MOCK"
    assert run["provider_mode"] == "fake"
    assert run["assessment"]["summary"]
    assert run["tool_calls_made"] >= 1
    assert any("tool" in t for t in run["trace"])
    assert "citations" in run and "guard_trace" in run
    # incident was auto-created and is auditable
    inc = state.incidents.get(run["incident_id"])
    assert inc.created_by == "orchestrator"
    assert inc.provenance["event_id"] == "evt-1"
    # run persisted to the shared investigations list
    assert state.investigation_runs[-1] is run


def test_duplicate_delivery_does_not_double_investigate(state):
    orch = state.orchestrator
    orch.enqueue(_event())
    assert orch.enqueue(_event()) == "duplicate"
    runs = orch.pump()
    assert len(runs) == 1
    assert orch.stats["duplicates"] == 1
    # redelivery after the run also dedupes (same resolved incident)
    assert orch.enqueue(_event()) == "duplicate"
    assert orch.pump() == []


def test_dedupe_key_includes_incident_id(state):
    orch = state.orchestrator
    inc_a = state.incidents.create("commander", "A", "")
    inc_b = state.incidents.create("commander", "B", "")
    assert orch.enqueue(_event(incident_id=inc_a.incident_id)) == "accepted"
    # same event_id, different incident -> distinct dedupe key
    assert orch.enqueue(_event(incident_id=inc_b.incident_id)) == "accepted"
    runs = orch.pump()
    assert {r["incident_id"] for r in runs} == {inc_a.incident_id,
                                              inc_b.incident_id}


def test_ignored_kinds_do_not_trigger(state):
    orch = state.orchestrator
    assert orch.enqueue(_event(kind="device_health")) == "ignored"
    assert orch.enqueue(_event(kind="contact_closed")) == "ignored"
    assert orch.pump() == []
    assert orch.stats["ignored"] == 2


def test_budget_exhaustion_stops_gracefully(state):
    orch = Orchestrator(state, max_tool_calls=1)
    orch.enqueue(_event())
    runs = orch.pump()
    assert len(runs) == 1
    run = runs[0]
    assert run["tool_calls_made"] <= 1
    assert run["budget_exhausted"] is True
    assert run["status"] in {"completed", "degraded", "rejected"}


def test_fabricated_citations_rejected(state):
    """A model citing evidence ids that were never produced must be
    rejected by ModelOutputGuard — not persisted as fact."""
    model = ScriptedModel([
        FakeResponse(tool_calls=[
            tc("get_evidence_metadata", {"evidence_id": "ev-1"}),
        ]),
        FakeResponse(tool_calls=[
            tc("append_agent_assessment", {
                "incident_id": "inc-x",
                "assessment": "attacker confirmed in rack-01",
                "evidence_ids": ["ev-fabricated-999"],
                "unknowns": ["intent"],
            }),
        ]),
        FakeResponse(content="done"),
    ])
    state.investigator_stack.model = model
    orch = Orchestrator(state)
    orch.enqueue(_event())
    run = orch.pump()[0]
    assert run["assessment_accepted"] is False
    assert run["status"] == "rejected"
    assert any("ev-fabricated-999" in v for v in run["assessment_violations"])


def test_authority_claim_rejected(state):
    """Model claiming executed containment is denied by the output guard."""
    model = ScriptedModel([
        FakeResponse(tool_calls=[
            tc("append_agent_assessment", {
                "incident_id": "inc-x",
                "assessment": "containment has been executed on lab-ap-01",
                "evidence_ids": ["ev-1"],
                "unknowns": ["u"],
            }),
        ]),
        FakeResponse(content="done"),
    ])
    state.investigator_stack.model = model
    orch = Orchestrator(state)
    orch.enqueue(_event())
    run = orch.pump()[0]
    assert run["assessment_accepted"] is False
    assert any("forbidden claim" in v for v in run["assessment_violations"])


def test_event_via_http_agent_token(client, auth, state):
    r = client.post("/internal/events", headers=auth["agent"], json={
        "event_id": "evt-http-1", "kind": "wifi_probe",
        "device_id": "device-lab-01", "zone_id": "rack-01",
        "summary": "probe request", "provenance": "MOCK"})
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "accepted"
    # human principals cannot push orchestrator events
    for role in ("commander", "observer"):
        r = client.post("/internal/events", headers=auth[role], json={
            "event_id": "evt-x", "kind": "motion"})
        assert r.status_code == 403
    # duplicate push dedupes
    r = client.post("/internal/events", headers=auth["agent"], json={
        "event_id": "evt-http-1", "kind": "wifi_probe"})
    assert r.json()["status"] == "duplicate"
    # Accepted HTTP events run automatically; a manual pump does not repeat it.
    r = client.post("/internal/orchestrator/pump", headers=auth["agent"])
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    run = state.investigation_runs[-1]
    assert run["event_id"] == "evt-http-1"
    assert run["trace"]
    # status endpoint reports stats
    r = client.get("/internal/orchestrator/status", headers=auth["agent"])
    assert r.json()["stats"]["duplicates"] == 1


def test_run_record_is_json_serializable(state):
    orch = state.orchestrator
    orch.enqueue(_event())
    run = orch.pump()[0]
    json.dumps(run)  # must not raise — records feed API responses
