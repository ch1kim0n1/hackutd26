"""OPS-37 chaos harness — PASS/FAIL/NOT_RUN honesty + artifacts."""
import json

import pytest

from chaos_harness import ChaosHarness


class R:
    def __init__(s, ok): s.ok = ok


class Relay:
    def __init__(s): s.seen = set()
    def ingest(s, ev):
        if ev["event_id"] in s.seen: return R(False)
        s.seen.add(ev["event_id"]); return R(True)


class IdP:
    def login(s, name): return None if name != "admin-1" else "tok"


class CP:
    def lab_reachable_services(s, who): return []


class Subs:
    def can_subscribe(s, u, r): return u in ("resp-1",) and r == "inc-1"


class Chat:
    @staticmethod
    def sanitize(t):
        import re
        return re.sub(r"<[^>]+>", "", t)


class Guard:
    def check_output(s, t):
        # returns True when dangerous output is detected+blocked
        low = t.lower()
        return "ignore previous" in low or "rm -rf" in low


class Loop:
    def process_next(s): return {"state": "FAILED", "stage": "verify"}


class FW:
    def __init__(s): s.e = False
    def estop(s): s.e = True
    def is_estopped(s): return s.e
    def can_move(s): return not s.e


@pytest.fixture
def h():
    return ChaosHarness(backends={
        "relay": Relay(), "idp": IdP(), "control_plane": CP(),
        "subscriptions": Subs(), "chat": Chat(), "model_guard": Guard(),
        "closed_loop": Loop(), "firmware": FW()})


def test_all_pass_with_good_backends(h):
    rep = h.run_all()
    assert rep["summary"]["PASS"] == 8
    assert rep["summary"]["FAIL"] == 0


def test_missing_backend_not_run(h):
    h2 = ChaosHarness(backends={})
    rep = h2.run_all()
    assert rep["summary"]["NOT_RUN"] == 8
    assert rep["summary"]["PASS"] == 0


def test_failing_scenario_marked_fail():
    class BadSubs:
        def can_subscribe(s, u, r): return True   # leaks!
    h = ChaosHarness(backends={"subscriptions": BadSubs()})
    r = h.run_scenario("private_subscription")
    assert r.status == "FAIL"


def test_artifacts_written(h, tmp_path):
    paths = h.write_artifacts(tmp_path)
    assert all(p.exists() for p in paths)
    rep = json.loads(paths[0].read_text())
    assert rep["summary"]["total"] == 8
    assert "PASS" in paths[1].read_text()


def test_each_scenario_detects_breach():
    # event replay: relay that accepts dupes -> FAIL
    class OpenRelay:
        def ingest(s, ev): return R(True)
    h = ChaosHarness(backends={"relay": OpenRelay()})
    assert h.run_scenario("event_replay").status == "FAIL"
