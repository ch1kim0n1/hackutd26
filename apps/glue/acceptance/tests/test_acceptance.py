"""GLUE-06: W01-W05 acceptance runner — PASS/FAIL/NOT_RUN honesty."""
import json

import pytest

from acceptance import AcceptanceRunner


class FakeCP:
    def __init__(self):
        self._tok = None

    def lab_reachable_services(self, who):
        return [] if who == "lab_hostile" else ["dashboard"]

    def simulate_lab_disconnect(self):
        pass

    def management_health(self):
        return {s: {"status": "up"} for s in
                ["dashboard", "chat", "db", "evidence"]}

    def login(self, who):
        self._tok = f"tok-{who}"
        return self._tok

    def revoke_session(self, tok):
        self._tok = None

    def valid_session(self, tok):
        return False

    def request_containment(self, seg, prin, tok, action):
        return False, "no approval", None


class FakeRelay:
    def __init__(self):
        self.seen = set()

    def ingest(self, ev):
        class R:
            def __init__(s, ok): s.ok = ok
        eid = ev["event_id"]
        if eid in self.seen:
            return R(False)
        self.seen.add(eid)
        return R(True)


class FakeIdP:
    def __init__(self):
        self.users = {
            "resp-1": {"user_id": "resp-1", "role": "responder",
                       "kind": "human", "status": "active"},
            "obs-1": {"user_id": "obs-1", "role": "observer",
                      "kind": "human", "status": "active"},
            "puck-1": {"user_id": "puck-1", "role": "device",
                       "kind": "machine", "status": "active"},
        }
        self.sessions = {}
        self.audit = []
        self._seq = 0

    def _audit_add(self, op, uid):
        self._seq += 1
        return {"seq": self._seq, "operation": op, "target_id": uid}

    def add_user(self, actor, name, role, kind):
        self._seq += 1
        u = {"user_id": f"u-{name}-{self._seq}", "username": name,
             "role": role, "kind": kind, "status": "active"}
        self.users[u["user_id"]] = u
        return u

    def revoke_user(self, actor, uid):
        u = self.users.get(uid)
        if u:
            u["status"] = "revoked"
        self.sessions.pop(uid, None)

    def audit_trail(self, uid):
        return [self._audit_add("user_add", uid),
                self._audit_add("user_revoke", uid)]

    def authorize(self, uid, access, inc):
        u = self.users.get(uid, {})
        if u.get("status") != "active":
            return {"allowed": False, "reason": "revoked"}
        role = u.get("role", "observer")
        allowed = role in ("admin", "commander", "responder") and \
            access == "read_incident" and inc in ("inc-1",)
        return {"allowed": allowed, "reason": "test"}

    def login(self, name):
        u = self.users.get(name)
        if not u or u.get("kind") != "human" or \
                u.get("status") != "active":
            return None
        self.sessions[name] = "tok"
        return "tok"


@pytest.fixture
def runner():
    return AcceptanceRunner(backends={
        "control_plane": FakeCP(),
        "relay": FakeRelay(),
        "identity": FakeIdP(),
    })


def test_w01_w02_pass_on_good_backends(runner):
    rep = runner.run_all()
    w01 = [i for i in rep["items"] if i["req"].startswith("W01")]
    w02 = [i for i in rep["items"] if i["req"].startswith("W02")]
    assert all(i["status"] == "PASS" for i in w01), w01
    assert all(i["status"] == "PASS" for i in w02), w02
    # W03-05 NOT_RUN — backends absent, honestly reported
    w345 = [i for i in rep["items"] if i["req"].startswith(("W03", "W04",
                                                          "W05"))]
    assert all(i["status"] == "NOT_RUN" for i in w345)
    assert "NOT CLAIMED" in rep["summary"]["deployment_acceptance"]


def test_missing_backend_is_not_run_not_pass():
    rep = AcceptanceRunner(backends={}).run_all()
    assert all(i["status"] == "NOT_RUN" for i in rep["items"])
    assert rep["summary"]["NOT_RUN"] == rep["summary"]["total"]


def test_failing_backend_marks_fail():
    class BadCP(FakeCP):
        def lab_reachable_services(self, who):
            return ["dashboard", "admin"]   # lab pivoted!
    rep = AcceptanceRunner(backends={"control_plane": BadCP(),
                                     "relay": FakeRelay(),
                                     "identity": FakeIdP()}).run_all()
    w01a = [i for i in rep["items"] if i["req"] == "W01a"][0]
    assert w01a["status"] == "FAIL"


def test_report_is_json_serializable(runner):
    rep = runner.run_all()
    json.dumps(rep)   # must not raise
    assert rep["summary"]["total"] == len(rep["items"])
