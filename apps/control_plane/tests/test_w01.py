"""W01a-e adversarial tests — docs/06 acceptance criteria.

Each test maps to a Winstead check; all run without real network."""
import hashlib
import hmac
import json

import pytest

from control_plane import (
    ControlPlane,
    LabRelay,
    Principal,
    Segment,
    Service,
    authorize,
)

SECRET = b"device-secret-1"


def signed_event(device_id="puck-a-01", seq=1, event_id="evt-1",
                 secret=SECRET, **over):
    ev = {"schema_version": 1, "event_id": event_id, "device_id": device_id,
          "seq": seq, "observed_at": "2026-11-07T20:00:00Z",
          "kind": "wifi_ap_seen", "zone_id": "rack-01",
          "data": {"ssid": "X", "bssid": "aa:bb", "channel": 6,
                   "rssi_dbm": -50}}
    ev.update(over)
    body = json.dumps({k: v for k, v in ev.items()},
                      sort_keys=True, separators=(",", ":")).encode()
    ev["signature"] = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return ev


def make_relay():
    r = LabRelay()
    r.issue_token("puck-a-01", "telemetry:ingest", SECRET)
    return r


# ---------- W01a: adversarial lab endpoint denied everything ----------

def test_w01a_lab_hostile_denied_all_services():
    for svc in Service:
        ok, reason = authorize(Segment.LAB, Principal.LAB_HOSTILE, svc)
        assert not ok, f"lab hostile reached {svc}"


def test_w01a_compromised_endpoint_cannot_use_human_roles():
    # device principal on lab segment still denied dashboard/chat/admin
    for svc in (Service.DASHBOARD_API, Service.CHAT, Service.ADMIN,
                Service.SPACETIMEDB, Service.CONTAINMENT):
        ok, _ = authorize(Segment.LAB, Principal.DEVICE, svc)
        assert not ok


# ---------- W01b: lab network failure, control plane unaffected ----------

def test_w01b_lab_disconnect_management_still_up():
    cp = ControlPlane()
    cp.lab_connected = False
    # all management services still healthy; lab link honestly stale
    for svc in Service:
        h = cp.service_health(svc)
        assert h["status"] == "up"
        assert h["lab_link"] == "disconnected_stale"
    # operator can still read (cached) — writes to lab-dependent paths
    # would be gated by relay fail-closed (see relay tests)


# ---------- W01c: replay + forged command ----------

def test_w01c_replay_and_forgery_dropped():
    r = make_relay()
    ev = signed_event()
    assert r.ingest(ev).ok
    # exact replay -> duplicate event_id
    assert not r.ingest(ev).ok
    assert "duplicate" in r.rejected[-1][1]
    # forged signature
    bad = signed_event(event_id="evt-2", seq=2, secret=b"wrong")
    assert not r.ingest(bad).ok
    assert "signature" in r.rejected[-1][1]
    # stale seq
    old = signed_event(event_id="evt-3", seq=1)
    assert not r.ingest(old).ok
    assert "seq" in r.rejected[-1][1]


def test_w01c_relay_fail_closed_on_dependency_outage():
    r = make_relay()
    r.identity_ok = False
    res = r.ingest(signed_event())
    assert not res.ok and "dependency down" in res.reason
    r.identity_ok = True
    r.audit_ok = False
    res = r.ingest(signed_event(event_id="evt-x", seq=1))
    assert not res.ok and res.stale


# ---------- W01d: revoked/expired token denied immediately ----------

def test_w01d_revoked_and_expired_sessions_denied():
    cp = ControlPlane()
    tok = cp.login(Principal.OPERATOR)
    # valid while live
    ok, _ = cp.check_access(Segment.MANAGEMENT, Principal.OPERATOR,
                            Service.DASHBOARD_API, token=tok)
    assert ok
    cp.revoke_session(tok)
    ok, reason = cp.check_access(Segment.MANAGEMENT, Principal.OPERATOR,
                                 Service.DASHBOARD_API, token=tok)
    assert not ok
    # expired
    now = [1000.0]
    cp2 = ControlPlane(clock=lambda: now[0])
    tok2 = cp2.login(Principal.OPERATOR, ttl_s=10)
    now[0] += 11
    ok, _ = cp2.check_access(Segment.MANAGEMENT, Principal.OPERATOR,
                             Service.CHAT, token=tok2)
    assert not ok


# ---------- W01e: direct containment call refused ----------

def test_w01e_direct_containment_denied_without_approval():
    cp = ControlPlane()
    tok = cp.login(Principal.OPERATOR)
    action = {"action_type": "isolate_endpoint", "target_id": "lab-01",
              "incident_id": "inc-1", "approval_id": "fake"}
    ok, reason, _ = cp.request_containment(
        Segment.MANAGEMENT, Principal.OPERATOR, tok, action)
    assert not ok and "approval" in reason.lower()


def test_w01e_approved_action_accepted_then_fingerprint_bound():
    cp = ControlPlane()
    tok = cp.login(Principal.OPERATOR)
    action = {"action_type": "isolate_endpoint", "target_id": "lab-01",
              "incident_id": "inc-1"}
    cp.register_approval("appr-1", action)
    ok, reason, aid = cp.request_containment(
        Segment.MANAGEMENT, Principal.OPERATOR, tok,
        {**action, "approval_id": "appr-1"})
    assert ok and aid == "appr-1"
    # tampered target -> fingerprint mismatch
    ok, reason, _ = cp.request_containment(
        Segment.MANAGEMENT, Principal.OPERATOR, tok,
        {**action, "approval_id": "appr-1", "target_id": "prod-db"})
    assert not ok and "fingerprint" in reason


def test_w01e_agent_cannot_self_approve_via_containment():
    cp = ControlPlane()
    tok = cp.login(Principal.AGENT)
    # agent reaches containment service but still needs server approval
    ok, reason, _ = cp.request_containment(
        Segment.MANAGEMENT, Principal.AGENT, tok,
        {"action_type": "x", "target_id": "t", "incident_id": "i",
         "approval_id": "none"})
    assert not ok
