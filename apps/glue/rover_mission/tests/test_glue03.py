"""GLUE-03: proposal->policy->gateway->rover->evidence->incident."""
import time

import pytest

from rover_mission import (
    EvidenceVault,
    Gateway,
    IncidentUpdater,
    MissionDenied,
    MissionExpired,
    MissionOrchestrator,
    MissionProposal,
    PolicyGate,
    RouteSurvey,
    RoverSim,
    Waypoint,
)


@pytest.fixture
def rig():
    survey = RouteSurvey()
    survey.add(Waypoint("wp-rack-01", 2.0, 1.0, tags=["tag-rack"]))
    survey.add(Waypoint("wp-lobby", 5.0, 5.0))
    gate = PolicyGate()
    orch = MissionOrchestrator(survey, gate, Gateway(), RoverSim(survey),
                               EvidenceVault(), IncidentUpdater())
    return survey, gate, orch


def proposal(wp="wp-rack-01", inc="inc-1"):
    return MissionProposal(f"prop-{wp}", inc, wp, "inspect rack")


def approved(gate, p):
    gate.approve("appr-1", p)
    return "appr-1"


def test_full_loop(rig):
    _, gate, orch = rig
    p = proposal()
    aid = approved(gate, p)
    res = orch.run(p, aid)
    assert res["state"] == "complete"
    assert res["pose"] == (2.0, 1.0)
    assert res["photo"]["tag_seen"] == "tag-rack"
    assert res["photo"]["synthetic"] is True       # labeled sim evidence
    assert len(res["photo"]["sha256"]) == 64
    # evidence ref resolvable via vault + incident updated
    assert res["evidence_ref"] in orch.vault.artifacts
    assert orch.updater.updates[-1]["evidence_id"] == res["evidence_ref"]
    assert orch.updater.updates[-1]["incident_id"] == "inc-1"


def test_no_approval_denied(rig):
    _, _, orch = rig
    with pytest.raises(MissionDenied, match="approval"):
        orch.run(proposal(), None)


def test_expired_approval_fails_closed(rig):
    _, gate, orch = rig
    p = proposal()
    aid = approved(gate, p)
    now = [time.time()]
    gate.clock = lambda: now[0]
    now[0] += 200                                   # past 120s TTL
    with pytest.raises(MissionExpired):
        orch.run(p, aid)


def test_unsurveyed_waypoint_denied(rig):
    survey, gate, orch = rig
    survey.waypoints["wp-secret"] = Waypoint(
        "wp-secret", 9.0, 9.0, surveyed=False)
    p = proposal(wp="wp-secret")
    aid = approved(gate, p)
    with pytest.raises(MissionDenied, match="surveyed"):
        orch.run(p, aid)


def test_approval_bound_to_target(rig):
    _, gate, orch = rig
    p1, p2 = proposal(), proposal(wp="wp-lobby")
    gate.approve("appr-1", p1)
    with pytest.raises(MissionDenied, match="different target"):
        orch.run(p2, "appr-1")


def test_vault_short_lived_urls(rig):
    _, _, orch = rig
    orch.vault.store({"artifact_id": "a1", "sha256": "x"})
    url = orch.vault.access_url("a1")
    assert "exp=" in url
    with pytest.raises(MissionDenied):
        orch.vault.access_url("nope")
