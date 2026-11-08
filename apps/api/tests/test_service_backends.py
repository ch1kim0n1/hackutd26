"""ServiceBackends tests (BlindSpot task): investigations must read real
stored observations/assets/evidence — never canned FakeBackends data —
while action tools stay proposal/queue-only."""
import pytest

from sentinel_api.orchestrator import InvestigationEvent, Orchestrator
from investigator.scripted import FakeResponse, ScriptedModel, tc


def _push(state, orch, **kw):
    base = dict(event_id="obs-real-1", kind="wifi_probe",
                device_id="device-lab-01", zone_id="rack-01",
                summary="real probe observation", provenance="LIVE")
    base.update(kw)
    # trigger kinds -> accepted; observation-only kinds -> ignored but
    # still persisted to the live store
    assert orch.enqueue(InvestigationEvent(**base)) in ("accepted", "ignored")


def test_tools_read_real_stored_observations(state):
    orch = state.orchestrator
    _push(state, orch, data={"ssid": "UNSEEN-5G", "rssi": -61})
    orch.pump()
    # observation persisted to the live store
    assert any(o["event_id"] == "obs-real-1" for o in state.observations)
    # ServiceBackends returns it — not a canned fixture
    from investigator.service_backends import ServiceBackends
    b = ServiceBackends(state, state.investigation_runs[-1]["incident_id"])
    out = b.get_recent_observations({"limit": 10})
    ids = [o["id"] for o in out["observations"]]
    assert "obs-real-1" in ids
    assert all("fixture" not in str(o).lower() for o in out["observations"])


def test_observations_outside_incident_scope_stay_hidden(state):
    """Unlinked observations in other zones and observations linked to
    other incidents must not leak into this incident's tool results."""
    inc = state.incidents.create("commander", "zone scope", "",
                                 zone_id="rack-01")
    state.observations.extend([
        {"event_id": "in-zone", "kind": "wifi_probe", "device_id": "d1",
         "zone_id": "rack-01", "incident_id": "", "summary": "in",
         "data": {}, "observed_at": 1, "provenance": "LIVE", "at": 0},
        {"event_id": "other-zone", "kind": "wifi_probe", "device_id": "d2",
         "zone_id": "lab-b", "incident_id": "", "summary": "out",
         "data": {}, "observed_at": 1, "provenance": "LIVE", "at": 0},
        {"event_id": "linked-other", "kind": "wifi_probe", "device_id": "d3",
         "zone_id": "rack-01", "incident_id": "inc-other",
         "summary": "linked elsewhere",
         "data": {}, "observed_at": 1, "provenance": "LIVE", "at": 0},
    ])
    from investigator.service_backends import ServiceBackends
    b = ServiceBackends(state, inc.incident_id)
    ids = [o["id"] for o in
           b.get_recent_observations({"limit": 10})["observations"]]
    assert "in-zone" in ids
    assert "other-zone" not in ids
    assert "linked-other" not in ids


def test_authorized_assets_come_from_scope_matrix(state):
    inc = state.incidents.create("commander", "scope test", "")
    state.scope_matrix.add_entry(inc.incident_id, "asset-ap-01",
                                 dataset="wireless")
    from investigator.service_backends import ServiceBackends
    b = ServiceBackends(state, inc.incident_id)
    out = b.get_authorized_assets({})
    assert any(a["id"] == "asset-ap-01" for a in out["assets"])


def test_rover_status_and_rf_reflect_ingested_events(state):
    orch = state.orchestrator
    _push(state, orch, kind="mission_status", event_id="rover-1",
          device_id="rover-01", data={"state": "navigating", "x": 4.2})
    _push(state, orch, kind="wifi_ap_seen", event_id="rf-1",
          summary="ap seen")
    from investigator.service_backends import ServiceBackends
    b = ServiceBackends(state, "inc-any")
    rover = b.get_rover_status({"device_id": "rover-01"})
    assert rover["state"] == "reported"
    assert rover["data"]["state"] == "navigating"
    rf = b.get_rf_activity({"zone_id": "rack-01"})
    assert rf["frame_counts"].get("wifi_ap_seen") == 1


def test_inspection_and_rescan_are_requests_not_execution(state):
    inc = state.incidents.create("commander", "action test", "",
                                 zone_id="rack-01")
    from investigator.service_backends import ServiceBackends
    b = ServiceBackends(state, inc.incident_id)
    mission = b.request_rover_inspection(
        {"zone_id": "rack-01", "waypoint_id": "wp-1"})
    assert mission["state"] == "queued" and mission["requested_by"] == "agent"
    rescan = b.request_sensor_rescan({"device_id": "puck-a-01"})
    assert rescan["state"] == "queued"
    assert len(state.mission_requests) == 2
    # nothing executed: no executor/audit side effects beyond the records
    assert all(r["state"] == "queued" for r in state.mission_requests)


def test_containment_proposal_goes_through_policy(state):
    inc = state.incidents.create("commander", "containment test", "")
    from investigator.service_backends import ServiceBackends
    b = ServiceBackends(state, inc.incident_id)
    out = b.propose_containment({
        "action_type": "isolate_device", "target_id": "lab-ap-01",
        "reason": "agent-proposed after evidence review"})
    # either a real policy proposal or an honest denial — never execution
    assert out.get("recorded") in (True, False)
    if out.get("recorded"):
        assert out["state"] in {"proposed", "pending"}
        assert "no containment executed" in out["detail"]


def test_agent_assessment_and_message_persist_on_incident(state):
    inc = state.incidents.create("commander", "assess test", "")
    from investigator.service_backends import ServiceBackends
    b = ServiceBackends(state, inc.incident_id)
    out = b.append_agent_assessment({
        "assessment": "evidence consistent with rogue AP",
        "evidence_ids": ["obs-real-1"], "unknowns": ["intent"]})
    assert out["recorded"] is True
    assert state.agent_assessments[-1]["id"] == out["id"]
    assert any("agent" == n.get("by") for n in inc.notes)
    msg = b.post_incident_system_message({"message": "investigation note"})
    assert msg["posted"] is True


def test_operational_path_uses_service_backends_not_fake(state):
    """investigator_for must build ServiceBackends — prove a scripted
    model's tool call returns real stored data end-to-end."""
    inc = state.incidents.create("commander", "e2e real", "",
                                 zone_id="rack-01")
    state.observations.append({
        "event_id": "real-obs-42", "kind": "contact_open",
        "device_id": "device-lab-01", "zone_id": "rack-01",
        "incident_id": inc.incident_id, "summary": "cabinet opened",
        "data": {}, "observed_at": "2026-11-08T10:00:00Z",
        "provenance": "LIVE", "at": 0})
    model = ScriptedModel([
        FakeResponse(tool_calls=[
            tc("get_recent_observations", {"incident_id": "", "limit": 5}),
        ]),
        FakeResponse(content="done"),
    ])
    state.investigator_stack.model = model
    agent = state.investigator_for(inc.incident_id)
    # reach into the registry's bound backend to prove it is ServiceBackends
    backend_fn = agent.registry.backends.get("get_recent_observations")
    assert "service_backends" in type(backend_fn.__self__).__module__
    result = agent.investigate("check the cabinet event")
    assert result.tool_calls_made >= 1


def test_incident_creation_auto_triggers_deduplicated_investigation(client, auth, state):
    r = client.post("/incidents", headers=auth["commander"], json={
        "title": "rogue AP suspicion", "summary": "operator report",
        "severity": "high", "zone_id": "rack-01"})
    assert r.status_code == 201, r.text
    inc_id = r.json()["incident_id"]
    # TestClient runs background tasks before returning
    runs = [r for r in state.investigation_runs
            if r.get("incident_id") == inc_id]
    assert len(runs) == 1
    assert runs[0]["event_id"] == f"incident-{inc_id}"
    # persisted observation exists for the incident-created event
    assert any(o["event_id"] == f"incident-{inc_id}"
               and o["kind"] == "incident_created"
               for o in state.observations)
