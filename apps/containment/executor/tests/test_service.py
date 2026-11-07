"""Tests for the HTTP bridge: payload mapping, honest status codes,
idempotent redelivery, revert path."""
import json
import threading
import time
import urllib.request

import pytest

from containment_executor import ExecState
from containment_executor.adapters import MockLabAdapter
from containment_executor.service import ExecutorService, make_handler, \
    item_from_payload
from http.server import ThreadingHTTPServer


def payload(**kw):
    doc = {
        "schema_version": 1,
        "action_id": "act-1",
        "incident_id": "inc-1",
        "type": "isolate_endpoint",
        "target_id": "lab-endpoint-01",
        "fingerprint": "fp-1",
        "approval_id": "appr-1",
    }
    doc.update(kw)
    return doc


def test_item_mapping():
    item = item_from_payload(payload(), 300)
    assert item.action_id == "act-1"
    assert item.action_type == "isolate_endpoint"
    assert item.target_id == "lab-endpoint-01"
    assert item.approved_by == "approval:appr-1"
    assert item.expires_at > time.time()


def test_item_rejects_missing_fields():
    with pytest.raises(ValueError):
        item_from_payload({"action_id": "x"}, 300)
    with pytest.raises(ValueError):
        item_from_payload(payload(schema_version=2), 300)


def test_verified_returns_200():
    svc = ExecutorService()
    code, body = svc.execute(payload())
    assert code == 200
    assert body["state"] == "verified"
    assert body["states"] == ["started", "api_acked", "verified"]


def test_failed_verification_returns_502():
    lab = MockLabAdapter(lie_about_success=True)
    svc = ExecutorService(lab=lab)
    code, body = svc.execute(payload())
    assert code == 502
    assert body["state"] == "failed"
    assert "verification" in body["states"] or body["state"] == "failed"


def test_redelivery_idempotent():
    svc = ExecutorService()
    c1, b1 = svc.execute(payload())
    c2, b2 = svc.execute(payload())
    assert c1 == c2 == 200
    assert b1["state"] == b2["state"] == "verified"
    assert len(svc.outbox.records) == 1


def test_unknown_revert_404():
    svc = ExecutorService()
    code, _ = svc.revert("nope")
    assert code == 404


def test_revert_after_execute():
    svc = ExecutorService()
    svc.execute(payload())
    code, body = svc.revert("act-1")
    assert code == 200
    assert body["state"] == "verified"
    # lab rule removed + endpoint reachable again
    assert "lab-endpoint-01" not in svc.lab.rules
    assert svc.lab.endpoint_up["lab-endpoint-01"] is True


# ---------- real HTTP round-trip ----------

def _serve(svc, token=""):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(svc, token))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, httpd.server_address[1]


def _post(port, path, doc, token=None):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(doc).encode(), method="POST",
        headers={"content-type": "application/json",
                 **({"authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_http_execute_health_revert():
    svc = ExecutorService()
    httpd, port = _serve(svc, token="sekrit")
    try:
        code, body = _post(port, "/execute", payload(), token="sekrit")
        assert code == 200 and body["state"] == "verified"
        # auth enforced
        code, _ = _post(port, "/execute", payload(action_id="act-2"))
        assert code == 401
        # healthz open
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/healthz", timeout=5) as r:
            assert json.loads(r.read())["ok"] is True
        # revert
        code, body = _post(port, "/revert", {"action_id": "act-1"},
                           token="sekrit")
        assert code == 200 and body["state"] == "verified"
    finally:
        httpd.shutdown()
