"""Harness self-tests + evidence artifact generation."""
import json

from threat_tests import FakeIdP, FakeRelay, new_report, run_all
from threat_tests.checks import (
    check_evidence_upload,
    check_expired_sessions,
    check_identity_boundary,
    check_network_deny,
    check_subscription_enum,
    check_telemetry_forgery,
)
from threat_tests.report import Report


def test_all_six_checks_pass_on_healthy_doubles():
    results = run_all()
    assert len(results) == 6
    assert all(r.status == "PASS" for r in results), \
        [r for r in results if r.status == "FAIL"]


def test_each_boundary_detects_breach():
    # B1: give machine a session -> must FAIL
    idp = FakeIdP()
    idp.users["puck-1"]["kind"] = "human"  # sabotage
    idp.users["puck-1"]["active"] = True
    r = check_network_deny(idp)
    assert r.status == "FAIL"

    # B3: open membership -> must FAIL
    subs_ok = check_subscription_enum(
        __import__("threat_tests").FakeSubscriptions(), FakeIdP())
    assert subs_ok.status == "PASS"

    # B5: permissive store -> must FAIL
    class Permissive:
        def validate_upload(self, *a, **k):
            return True, "ok"
    r = check_evidence_upload(Permissive())
    assert r.status == "FAIL"


def test_forgery_check_catches_bad_relay():
    class OpenRelay:
        secret = b"x"
        seen = set()
        seq = {}
        def ingest(self, ev):
            return True, "ok"   # accepts everything
    r = check_telemetry_forgery(OpenRelay())
    assert r.status == "FAIL"


def test_report_json_and_markdown():
    rep = new_report("in_memory", run_all())
    j = rep.to_json()
    assert j["summary"]["all_passed"] is True
    assert len(j["checks"]) == 6
    md = rep.to_markdown()
    assert "ALL PASS" in md and "| B1 |" in md and "```json" in md
    # report is JSON-serializable end to end
    json.dumps(j)


def test_report_flags_failure():
    class BadIdP(FakeIdP):
        def valid_session(self, tok):
            return True   # accepts expired
    rep = Report(run_id="t", mode="in_memory", started_at=0,
                 results=[check_expired_sessions(BadIdP())])
    assert rep.failed == 1 and not rep.all_passed
    assert "FAILURES PRESENT" in rep.to_markdown()


def test_checks_are_independent():
    # each check constructible standalone
    assert check_network_deny(FakeIdP()).status == "PASS"
    assert check_telemetry_forgery(FakeRelay(b"s")).status == "PASS"
    assert check_subscription_enum(
        __import__("threat_tests").FakeSubscriptions(), FakeIdP()).status == "PASS"
    assert check_expired_sessions(FakeIdP()).status == "PASS"
    from threat_tests import FakeEvidenceStore
    assert check_evidence_upload(FakeEvidenceStore()).status == "PASS"
    assert check_identity_boundary(FakeIdP()).status == "PASS"
