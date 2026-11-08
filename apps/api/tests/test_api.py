"""API facade tests — auth denial, schema rejection, happy paths,
RBAC scoping, version conflicts, proposal/approval SoD, provenance."""
import pytest


def _mk_incident(client, auth, role="commander", **kw):
    body = {"title": kw.pop("title", "Test incident"),
            "summary": "seeded test incident",
            "severity": kw.pop("severity", "high"),
            "zone_id": kw.pop("zone_id", "rack-01")}
    body.update(kw)
    r = client.post("/incidents", json=body, headers=auth[role])
    assert r.status_code == 201, r.text
    return r.json()


# ---------------- health / auth ----------------
def test_health_and_ready(client):
    assert client.get("/healthz").json()["status"] == "ok"
    r = client.get("/readyz")
    assert r.status_code == 200 and r.json()["ready"] is True
    assert r.json()["state_backend"] == "in-memory"


def test_missing_token_401(client):
    assert client.get("/incidents").status_code == 401
    assert client.get("/incidents",
                      headers={"Authorization": "Bearer bogus"}
                      ).status_code == 401


def test_machine_cannot_human_login(client):
    r = client.post("/auth/login", json={"username": "agent-01"})
    assert r.status_code == 401


def test_login_logout(client, tokens):
    r = client.post("/auth/login", json={"username": "observer"})
    tok = r.json()["token"]
    assert client.get("/incidents",
                      headers={"Authorization": f"Bearer {tok}"}
                      ).status_code == 200
    client.post("/auth/logout",
                headers={"Authorization": f"Bearer {tok}"})
    assert client.get("/incidents",
                      headers={"Authorization": f"Bearer {tok}"}
                      ).status_code == 401


# ---------------- incidents ----------------
def test_create_and_read_incident(client, auth, state):
    inc = _mk_incident(client, auth)
    assert inc["incident_id"].startswith("inc-")
    assert inc["provenance"] == "LIVE"
    assert inc["state_backend"] == "in-memory"
    r = client.get(f"/incidents/{inc['incident_id']}",
                   headers=auth["commander"])
    assert r.status_code == 200
    assert r.json()["title"] == "Test incident"


def test_observer_cannot_create(client, auth):
    r = client.post("/incidents",
                    json={"title": "nope", "severity": "low"},
                    headers=auth["observer"])
    assert r.status_code == 403


def test_scoped_responder_denied_then_granted(client, auth, state):
    inc = _mk_incident(client, auth)
    iid = inc["incident_id"]
    resp_uid = state.identity.users and next(
        u.user_id for u in state.identity.users.values()
        if u.username == "responder")
    # empty scope -> denied even though role has READ_INCIDENT
    r = client.get(f"/incidents/{iid}", headers=auth["responder"])
    assert r.status_code == 403
    # admin grants scope -> allowed
    client.post(f"/users/{resp_uid}/scope",
                json={"incident_ids": [iid]}, headers=auth["admin"])
    r = client.get(f"/incidents/{iid}", headers=auth["responder"])
    assert r.status_code == 200


def test_version_conflict_and_invalid_transition(client, auth):
    inc = _mk_incident(client, auth)
    iid = inc["incident_id"]
    r = client.patch(f"/incidents/{iid}",
                     json={"expected_version": 99,
                           "fields": {"title": "stale"}},
                     headers=auth["commander"])
    assert r.status_code == 409
    r = client.post(f"/incidents/{iid}/transition",
                    json={"to_state": "resolved", "expected_version": 1},
                    headers=auth["commander"])
    assert r.status_code == 409  # new -> resolved not allowed
    r = client.post(f"/incidents/{iid}/transition",
                    json={"to_state": "triage", "expected_version": 1},
                    headers=auth["commander"])
    assert r.status_code == 200
    assert r.json()["state"] == "triage"


def test_schema_rejection(client, auth):
    r = client.post("/incidents", json={}, headers=auth["commander"])
    assert r.status_code == 422
    r = client.post("/incidents",
                    json={"title": "x" * 300}, headers=auth["commander"])
    assert r.status_code == 422


def test_evidence_note_packet(client, auth):
    inc = _mk_incident(client, auth)
    iid = inc["incident_id"]
    client.post(f"/incidents/{iid}/evidence",
                json={"evidence_id": "ev-1", "kind": "observation",
                      "note": "rf scan"}, headers=auth["responder"])
    client.post(f"/incidents/{iid}/notes",
                json={"text": "looking into it"}, headers=auth["responder"])
    pkt = client.get(f"/incidents/{iid}/packet",
                     headers=auth["commander"])
    assert pkt.status_code == 200
    assert pkt.json()["incident"]["incident_id"] == iid


# ---------------- scope matrix ----------------
def test_scope_entries(client, auth):
    inc = _mk_incident(client, auth)
    iid = inc["incident_id"]
    r = client.post("/scope/entries",
                    json={"incident_id": iid, "asset_id": "rack-01",
                          "dataset": "file-share"},
                    headers=auth["commander"])
    assert r.status_code == 201
    entries = client.get(f"/incidents/{iid}/scope",
                         headers=auth["commander"]).json()["items"]
    assert len(entries) == 1 and entries[0]["asset_id"] == "rack-01"


# ---------------- investigation ----------------
def test_investigation_runs_scripted_agent(client, auth):
    inc = _mk_incident(client, auth)
    iid = inc["incident_id"]
    r = client.post("/investigations",
                    json={"incident_id": iid,
                          "brief": "unknown BLE device near rack-01"},
                    headers=auth["commander"])
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["summary"]
    assert a["tool_calls_made"] >= 1
    assert a["provenance"] == "LIVE"
    runs = client.get("/investigations",
                      headers=auth["commander"]).json()["items"]
    # incident creation auto-triggers one orchestrator run (incident_created)
    # plus this explicit run
    assert len(runs) == 2


# ---------------- proposals / approvals ----------------
def _grant_scope(client, auth, state, username, iid):
    uid = next(u.user_id for u in state.identity.users.values()
               if u.username == username)
    r = client.post(f"/users/{uid}/scope",
                    json={"incident_ids": [iid]}, headers=auth["admin"])
    assert r.status_code == 200, r.text


def _propose(client, auth, state=None, role="agent", iid=None, **kw):
    if iid is None:
        iid = _mk_incident(client, auth)["incident_id"]
    if role == "agent" and state is not None:
        _grant_scope(client, auth, state, "agent-01", iid)
    body = {"incident_id": iid, "action_type": "isolate_endpoint",
            "target_id": "lab-ap-01",
            "reason": "confirmed rogue AP fingerprint mismatch"}
    body.update(kw)
    return client.post("/proposals", json=body, headers=auth[role]), iid


def test_proposal_happy_and_approval(client, auth, state):
    r, iid = _propose(client, auth, state)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["state"] == "proposed" and p["fingerprint"]
    # agent cannot approve (lacks approve_action)
    r = client.post("/approvals",
                    json={"proposal_id": p["proposal_id"],
                          "decision": "approve",
                          "fingerprint": p["fingerprint"]},
                    headers=auth["agent"])
    assert r.status_code == 403
    # commander approves with bound fingerprint
    r = client.post("/approvals",
                    json={"proposal_id": p["proposal_id"],
                          "decision": "approve",
                          "fingerprint": p["fingerprint"]},
                    headers=auth["commander"])
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert r.json()["proposal"]["state"] == "approved"


def test_proposal_target_allowlist_and_reason(client, auth, state):
    r, _ = _propose(client, auth, state, target_id="evil-host-99")
    assert r.status_code == 403
    r, _ = _propose(client, auth, state, reason="short")
    assert r.status_code in (403, 422)


def test_self_approval_denied(client, auth):
    # commander can propose; approving own proposal violates SoD
    r, _ = _propose(client, auth, role="commander")
    p = r.json()
    r = client.post("/approvals",
                    json={"proposal_id": p["proposal_id"],
                          "decision": "approve",
                          "fingerprint": p["fingerprint"]},
                    headers=auth["commander"])
    assert r.status_code == 403
    assert "separation" in r.json()["detail"]["reason"] or \
        "separation" in str(r.json())


def test_bad_fingerprint_rejected(client, auth, state):
    r, _ = _propose(client, auth, state)
    p = r.json()
    r = client.post("/approvals",
                    json={"proposal_id": p["proposal_id"],
                          "decision": "approve",
                          "fingerprint": "0" * 64},
                    headers=auth["commander"])
    assert r.status_code == 403


# ---------------- executor + audit ----------------
def test_approved_feed_and_executor_roles(client, auth, state):
    # observer cannot read approved feed
    assert client.get("/actions/approved",
                      headers=auth["observer"]).status_code == 403
    r, _ = _propose(client, auth, state)
    p = r.json()
    client.post("/approvals",
                json={"proposal_id": p["proposal_id"],
                      "decision": "approve",
                      "fingerprint": p["fingerprint"]},
                headers=auth["commander"])
    feed = client.get("/actions/approved",
                      headers=auth["commander"]).json()["items"]
    assert any(i["proposal_id"] == p["proposal_id"] for i in feed)
    # observer cannot execute
    assert client.post("/executor/execute", json={"doc": {}},
                       headers=auth["observer"]).status_code == 403


def test_audit_restricted_and_records_denials(client, auth):
    # provoke a denial so the audit trail has an entry
    client.get("/incidents", headers={"Authorization": "Bearer bad"})
    r = client.get("/audit", headers=auth["observer"])
    assert r.status_code == 403
    r = client.get("/audit", headers=auth["commander"])
    assert r.status_code == 200
    assert r.json()["chain_valid"] is True
    assert len(r.json()["identity_audit"]) > 0
