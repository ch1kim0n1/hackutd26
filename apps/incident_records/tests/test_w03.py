"""W03a-e — incident records: live editing, conflicts, evidence,
export, audit history."""
import pytest

from incident_records import (
    IncidentService,
    IncidentState,
    InvalidTransition,
    Severity,
    VersionConflict,
)


@pytest.fixture
def svc():
    return IncidentService()


def make(svc, title="Suspicious AP near rack-01", **kw):
    return svc.create("alice", title,
                      severity=Severity.HIGH, zone_id="rack-01",
                      provenance={"source": "correlator", "trace_id": "t-1"},
                      **kw)


# ---------- W03a: two-user live editing with visible conflicts ----------

def test_w03a_concurrent_edit_conflict_visible(svc):
    inc = make(svc)
    v1 = inc.version
    # user A edits at v1 -> succeeds, bumps to v2
    svc.update(inc.incident_id, "alice", v1, {"severity": Severity.CRITICAL})
    # user B still holding v1 -> VersionConflict, NOT silent overwrite
    with pytest.raises(VersionConflict) as e:
        svc.update(inc.incident_id, "bob", v1, {"title": "hijacked"})
    assert e.value.current_version == v1 + 1
    # B retries with fresh version -> succeeds, both edits preserved
    cur = svc.get(inc.incident_id).version
    svc.update(inc.incident_id, "bob", cur, {"confidence": 0.9})
    final = svc.get(inc.incident_id)
    assert final.severity == Severity.CRITICAL   # A's edit kept
    assert final.confidence == 0.9               # B's edit applied
    assert final.title == "Suspicious AP near rack-01"  # no overwrite


def test_w03a_non_editable_fields_rejected(svc):
    inc = make(svc)
    with pytest.raises(ValueError):
        svc.update(inc.incident_id, "alice", inc.version,
                   {"state": "closed", "version": 99})


# ---------- W03b: evidence + history ----------

def test_w03b_evidence_links_and_timeline(svc):
    inc = make(svc)
    svc.link_evidence(inc.incident_id, "alice", "ev-1", "rf_frame",
                      note="deauth burst")
    svc.link_evidence(inc.incident_id, "bob", "ev-2", "artifact",
                      note="pcap slice")
    svc.add_note(inc.incident_id, "alice", "onsite check scheduled")
    final = svc.get(inc.incident_id)
    assert len(final.evidence) == 2
    assert final.evidence[0].added_by == "alice"
    kinds = [t.kind for t in final.timeline]
    assert kinds == ["created", "evidence_add", "evidence_add", "note"]
    # timeline is append-only ordered
    assert [t.seq for t in final.timeline] == [1, 2, 3, 4]


# ---------- W03c: state machine ----------

def test_w03c_valid_and_invalid_transitions(svc):
    inc = make(svc)
    v = inc.version
    svc.transition(inc.incident_id, "alice", IncidentState.TRIAGE, v,
                   reason="acknowledged")
    v = svc.get(inc.incident_id).version
    svc.transition(inc.incident_id, "alice", IncidentState.INVESTIGATING, v)
    # illegal: investigating -> closed directly
    v = svc.get(inc.incident_id).version
    with pytest.raises(InvalidTransition):
        svc.transition(inc.incident_id, "alice", IncidentState.CLOSED, v)
    # terminal state has no exits
    inc2 = make(svc, title="x")
    iid = inc2.incident_id
    for to in (IncidentState.TRIAGE, IncidentState.DISMISSED):
        cur = svc.get(iid).version
        svc.transition(iid, "alice", to, cur)
    cur = svc.get(iid).version
    with pytest.raises(InvalidTransition):
        svc.transition(iid, "alice", IncidentState.NEW, cur)


# ---------- W03d: incident packet export ----------

def test_w03d_export_packet_complete(svc):
    inc = make(svc)
    svc.update(inc.incident_id, "alice", inc.version,
               {"owner_id": "cmd-1", "confidence": 0.75})
    svc.link_evidence(inc.incident_id, "alice", "ev-9", "observation")
    packet = svc.export_packet(inc.incident_id, "alice")
    assert packet["incident"]["incident_id"] == inc.incident_id
    assert packet["incident"]["provenance"]["trace_id"] == "t-1"
    assert len(packet["evidence"]) == 1
    assert len(packet["timeline"]) >= 3
    # export itself is a timeline event (auditable)
    assert svc.get(inc.incident_id).timeline[-1].kind == "export"
    md = svc.export_markdown(inc.incident_id, "alice")
    assert "# Incident" in md and "## Timeline" in md and "ev-9" in md


def test_w03d_confidence_clamped(svc):
    inc = make(svc)
    svc.update(inc.incident_id, "alice", inc.version,
               {"confidence": 1.7})
    assert svc.get(inc.incident_id).confidence == 1.0
