import pytest

from investigator import (
    FakeBackends,
    FakeResponse,
    InvestigationAgent,
    ScriptedModel,
    ToolContext,
    ToolRegistry,
    tc,
)

CTX = ToolContext(
    incident_id="inc-1",
    allowed_zones={"rack-01"},
    allowed_waypoints={"wp-rack-01"},
    allowed_devices={"puck-a-01", "puck-b-01", "rover-01"},
)


def make_agent(responses, backends=None):
    be = backends or FakeBackends()
    reg = ToolRegistry(CTX, be.as_backends())
    model = ScriptedModel(responses)
    return InvestigationAgent(model, reg), be, model, reg


def test_full_investigation_with_rover_inspection():
    """N01-style: >=3 real tool calls incl. rover inspection; cites evidence."""
    responses = [
        FakeResponse(tool_calls=[
            tc("get_recent_observations", {"incident_id": "inc-1", "limit": 5}, "c1"),
            tc("get_authorized_assets", {"zone_id": "rack-01"}, "c2"),
        ]),
        FakeResponse(tool_calls=[
            tc("get_rf_activity", {"zone_id": "rack-01", "time_window_s": 300}, "c3"),
            tc("request_rover_inspection", {"zone_id": "rack-01",
                                            "waypoint_id": "wp-rack-01"}, "c4"),
        ]),
        FakeResponse(tool_calls=[
            tc("get_evidence_metadata", {"evidence_id": "ev-1"}, "c5"),
            tc("append_agent_assessment",
               {"incident_id": "inc-1",
                "assessment": "Unknown BSSID on known SSID + unauthorized "
                              "cabinet open; consistent with rogue AP test "
                              "or tamper — NOT confirmed exfiltration.",
                "evidence_ids": ["obs-1", "obs-2", "ev-1"],
                "unknowns": ["who opened cabinet", "is BSSID attacker-owned"]},
               "c6"),
        ]),
        FakeResponse(content="Assessment appended."),
    ]
    agent, be, model, reg = make_agent(responses)
    out = agent.investigate("CORR01 candidate in rack-01")
    # >=3 real tool calls including rover inspection
    assert out.tool_calls_made >= 5
    assert len(be.missions) == 1
    assert be.missions[0]["type"] == "inspect_zone"
    assert be.missions[0]["waypoint_id"] == "wp-rack-01"
    # assessment recorded with evidence ids + unknowns
    assert len(be.assessments) == 1
    assert "obs-1" in be.assessments[0]["evidence_ids"]
    assert be.assessments[0]["unknowns"]
    assert "exfiltration" not in be.assessments[0]["assessment"].lower() or \
        "NOT confirmed" in be.assessments[0]["assessment"]
    # trace complete
    assert len(out.trace) >= 3
    assert any(t.get("tool") == "request_rover_inspection" for t in out.trace)


def test_rover_inspection_out_of_scope_denied():
    """N06: unauthorized waypoint refused — mission never queued."""
    responses = [FakeResponse(tool_calls=[
        tc("request_rover_inspection", {"zone_id": "rack-01",
                                        "waypoint_id": "wp-evil-99"}, "c1")]),
        FakeResponse(content="done")]
    agent, be, *_ = make_agent(responses)
    agent.investigate("test")
    assert be.missions == []
    denied = [c for c in agent.registry.calls
              if c["tool"] == "request_rover_inspection" and c.get("denied")]
    assert denied and "outside incident scope" in denied[0]["error"]


def test_unknown_tool_denied():
    reg = ToolRegistry(CTX, FakeBackends().as_backends())
    r = reg.call("run_shell_command", {"cmd": "rm -rf /"})
    assert not r.ok and r.denied
    assert "not in allowlist" in r.error


def test_extra_args_rejected():
    reg = ToolRegistry(CTX, FakeBackends().as_backends())
    r = reg.call("get_rover_status",
                 {"device_id": "rover-01", "sudo": True})
    assert not r.ok and "unexpected args" in r.error


def test_wrong_incident_scope_denied():
    reg = ToolRegistry(CTX, FakeBackends().as_backends())
    r = reg.call("get_recent_observations",
                 {"incident_id": "inc-OTHER", "limit": 5})
    assert not r.ok and r.denied


def test_model_outage_degrades_not_crashes():
    class Down:
        def chat(self, *a, **k):
            raise ConnectionError("endpoint down")

    be = FakeBackends()
    reg = ToolRegistry(CTX, be.as_backends())
    agent = InvestigationAgent(Down(), reg)
    out = agent.investigate("test")
    assert out.degraded and out.degrade_reason
    # manual workflow unaffected — no missions fired, no crash
    assert be.missions == []


def test_tool_call_budget_enforced():
    # model that always asks for observations — budget caps at max_tool_calls
    responses = [FakeResponse(tool_calls=[
        tc("get_recent_observations", {"incident_id": "inc-1"}, f"c{i}")])
        for i in range(30)]
    agent, be, *_ = make_agent(responses)
    agent.max_tool_calls = 5
    out = agent.investigate("loop")
    assert out.tool_calls_made <= 5
    assert len(be.calls.get("get_recent_observations", [])) <= 5


def test_propose_containment_is_proposal_only():
    responses = [
        FakeResponse(tool_calls=[
            tc("propose_containment",
               {"incident_id": "inc-1", "action_type": "isolate_endpoint",
                "target_id": "lab-endpoint-01", "reason": "confirmed rogue AP"},
               "c1")]),
        FakeResponse(content="proposed"),
    ]
    agent, be, *_ = make_agent(responses)
    agent.investigate("test")
    assert len(be.proposals) == 1
    assert be.proposals[0]["state"] == "proposed"  # never approved/executed
