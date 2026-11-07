"""W04a-e — compromised-data scope matrix."""
import pytest

from scope_matrix import (
    CIA,
    InsufficientEvidence,
    ScopeMatrix,
    ScopeStatus,
    VersionConflict,
)


@pytest.fixture
def mx():
    return ScopeMatrix()


def entry(mx, asset="fs-01", dataset="hr-records", inc="inc-1"):
    return mx.add_entry(inc, asset, dataset, by="cmd-1")


# ---------- W04a: commander edits, responders see live updates ----------

def test_w04a_versioned_live_updates(mx):
    e = entry(mx)
    v = e.version
    # commander edits confidentiality -> suspected_exposed w/ weak ev ok
    mx.set_status(e.entry_id, "cmd-1", v, CIA.CONFIDENTIALITY,
                  ScopeStatus.SUSPECTED_EXPOSED,
                  evidence_kind="rf_frame", evidence_ref="rf-1",
                  reason="rogue AP near file server")
    # responder reads -> sees update immediately (same object store)
    seen = mx.get(e.entry_id)
    assert seen.cia[CIA.CONFIDENTIALITY] == ScopeStatus.SUSPECTED_EXPOSED
    assert seen.version == v + 1
    # stale writer conflicts visibly
    with pytest.raises(VersionConflict):
        mx.set_status(e.entry_id, "resp-1", v, CIA.INTEGRITY,
                      ScopeStatus.UNAFFECTED)


# ---------- W04b: ransomware vs exfiltration are different cases ----------

def test_w04b_ransomware_and_exfil_distinct(mx):
    enc = entry(mx, asset="fs-02", dataset="finance-db")
    exf = entry(mx, asset="web-01", dataset="customer-pii")
    # ransomware: availability+confidentiality locked, integrity ok
    mx.set_status(enc.entry_id, "cmd-1", enc.version, CIA.AVAILABILITY,
                  ScopeStatus.ENCRYPTED_LOCKED, evidence_kind="ransom_note",
                  evidence_ref="note-1")
    mx.set_status(enc.entry_id, "cmd-1", mx.get(enc.entry_id).version,
                  CIA.CONFIDENTIALITY, ScopeStatus.ENCRYPTED_LOCKED,
                  evidence_kind="ransom_note", evidence_ref="note-1")
    mx.set_status(enc.entry_id, "cmd-1", mx.get(enc.entry_id).version,
                  CIA.INTEGRITY, ScopeStatus.UNAFFECTED,
                  evidence_kind="backup_diff", evidence_ref="diff-1")
    # exfil: confidentiality exfiltrated, integrity/availability fine
    mx.set_status(exf.entry_id, "cmd-1", exf.version, CIA.CONFIDENTIALITY,
                  ScopeStatus.EXFILTRATED, evidence_kind="exfil_capture",
                  evidence_ref="cap-1")
    mx.set_status(exf.entry_id, "cmd-1", mx.get(exf.entry_id).version,
                  CIA.INTEGRITY, ScopeStatus.UNAFFECTED)
    mx.set_status(exf.entry_id, "cmd-1", mx.get(exf.entry_id).version,
                  CIA.AVAILABILITY, ScopeStatus.UNAFFECTED)
    a, b = mx.get(enc.entry_id), mx.get(exf.entry_id)
    assert a.cia[CIA.AVAILABILITY] == ScopeStatus.ENCRYPTED_LOCKED
    assert a.cia[CIA.INTEGRITY] == ScopeStatus.UNAFFECTED
    assert b.cia[CIA.CONFIDENTIALITY] == ScopeStatus.EXFILTRATED
    assert b.cia[CIA.AVAILABILITY] == ScopeStatus.UNAFFECTED
    # estimated impacts visibly differ
    mx.set_impact(enc.entry_id, "cmd-1", a.version, record_count=50000,
                  window_start=1000, window_end=2000)
    mx.set_impact(exf.entry_id, "cmd-1", b.version, record_count=12000,
                  window_start=500, window_end=900)
    assert mx.get(enc.entry_id).record_count_estimate == 50000
    assert mx.get(exf.entry_id).record_count_estimate == 12000


# ---------- W04c: statuses + estimated impacts independently editable ----------

def test_w04c_independent_cia_dimensions(mx):
    e = entry(mx)
    mx.set_status(e.entry_id, "cmd-1", e.version, CIA.CONFIDENTIALITY,
                  ScopeStatus.CONFIRMED_EXPOSED, evidence_kind="auth_log",
                  evidence_ref="auth-1")
    # availability independently marked unavailable
    cur = mx.get(e.entry_id).version
    mx.set_status(e.entry_id, "cmd-1", cur, CIA.AVAILABILITY,
                  ScopeStatus.UNAVAILABLE, evidence_kind="manual_verified")
    # integrity stays unknown — NEVER auto-flipped
    cur = mx.get(e.entry_id).version
    s = mx.get(e.entry_id).status_summary()
    assert s["confidentiality"] == "confirmed_exposed"
    assert s["availability"] == "unavailable"
    assert s["integrity"] == "unknown"   # unknown preserved, not "unaffected"


# ---------- W04d: evidence-linked + auditable; suspected != confirmed ----------

def test_w04d_evidence_gating_and_audit(mx):
    e = entry(mx)
    # RF/AP event CANNOT confirm breach — InsufficientEvidence
    with pytest.raises(InsufficientEvidence):
        mx.set_status(e.entry_id, "cmd-1", e.version, CIA.CONFIDENTIALITY,
                      ScopeStatus.CONFIRMED_EXPOSED,
                      evidence_kind="rf_frame", evidence_ref="rf-9")
    with pytest.raises(InsufficientEvidence):
        mx.set_status(e.entry_id, "cmd-1", e.version, CIA.CONFIDENTIALITY,
                      ScopeStatus.EXFILTRATED, evidence_kind="wifi_ap")
    # suspected IS allowed with weak evidence
    mx.set_status(e.entry_id, "cmd-1", e.version, CIA.CONFIDENTIALITY,
                  ScopeStatus.SUSPECTED_EXPOSED, evidence_kind="rf_frame",
                  evidence_ref="rf-9")
    # strong evidence upgrades to confirmed
    cur = mx.get(e.entry_id).version
    mx.set_status(e.entry_id, "cmd-1", cur, CIA.CONFIDENTIALITY,
                  ScopeStatus.EXFILTRATED, evidence_kind="exfil_capture",
                  evidence_ref="cap-2")
    s = mx.get(e.entry_id).status_summary()
    assert s["confidentiality"] == "exfiltrated"
    assert "cap-2" in mx.get(e.entry_id).evidence_refs
    # every change audited with from->to
    ops = [a for a in mx.audit if a["op"] == "status_change"]
    assert len(ops) >= 2
    assert ops[-1]["detail"]["to"] == "exfiltrated"


# ---------- W04e: snapshots preserve earlier states ----------

def test_w04e_snapshots_preserve_history(mx):
    e = entry(mx)
    mx.set_status(e.entry_id, "cmd-1", e.version, CIA.CONFIDENTIALITY,
                  ScopeStatus.SUSPECTED_EXPOSED, evidence_kind="rf_frame")
    snap1 = mx.snapshot("cmd-1", reason="pre-investigation")
    cur = mx.get(e.entry_id).version
    mx.set_status(e.entry_id, "cmd-1", cur, CIA.CONFIDENTIALITY,
                  ScopeStatus.EXFILTRATED, evidence_kind="exfil_capture")
    snap2 = mx.snapshot("cmd-1", reason="confirmed exfil")
    # earlier snapshot still shows suspected, not retroactively changed
    assert snap1.entries[e.entry_id]["cia"]["confidentiality"] == \
        "suspected_exposed"
    assert snap2.entries[e.entry_id]["cia"]["confidentiality"] == "exfiltrated"
    assert len(mx.snapshots) == 2
