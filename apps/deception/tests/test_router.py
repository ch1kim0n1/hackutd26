import json
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "deception" / "src"))
sys.path.insert(0, str(ROOT / "defense" / "gateway" / "src"))

from deception import DeceptionRouter, deception_policy, flow  # noqa: E402
from defense_gateway.engine import DecisionEngine  # noqa: E402

# minimal decoy stand-in matching #107's contract (synthetic flag +
# device_id + decoy trace_id) — package merges separately
import http.server  # noqa: E402


class _Decoy(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        out = json.dumps({"device_id": "decoy-01", "synthetic": True,
                          "trace_id": "decoy-test-1"}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


def decoy_server(host, port):
    return http.server.HTTPServer((host, port), _Decoy)


@pytest.fixture()
def lab():
    """Real decoy + stub backend, evidence collected."""
    decoy = decoy_server("127.0.0.1", 0)
    decoy_port = decoy.server_address[1]

    # stub 'real' backend: returns JSON marker
    class B(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            out = b'{"svc":"real-backend"}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
        def log_message(self, *a):
            pass
    backend = http.server.HTTPServer(("127.0.0.1", 0), B)
    bport = backend.server_address[1]
    for srv in (decoy, backend):
        threading.Thread(target=srv.serve_forever, daemon=True).start()

    evidence = []
    policy = deception_policy(
        redirect_src_nodes=("attacker-01",),
        block_src_nodes=("bad-actor",),
        default="monitor")
    router = DeceptionRouter(
        engine=DecisionEngine(policy),
        backends={"vpi-01": f"http://127.0.0.1:{bport}"},
        decoy_url=f"http://127.0.0.1:{decoy_port}",
        evidence_sink=evidence.append)
    yield router, evidence
    decoy.shutdown(); backend.shutdown()


def body_json(res):
    return json.loads(res.body)


def test_redirect_goes_to_decoy(lab):
    router, ev = lab
    f = flow("f1", "attacker-01", "vpi-01")
    res = router.route(f, "/login")
    assert res.action == "redirect"
    assert res.status == 200
    assert body_json(res)["device_id"] == "decoy-01"
    assert body_json(res)["synthetic"] is True
    # trace id preserved through decoy
    assert res.evidence["decoy"]["decoy_trace"]
    assert ev and ev[-1]["outcome"] == "decoy_hit"


def test_block_never_reaches_anything(lab):
    router, ev = lab
    res = router.route(flow("f2", "bad-actor", "vpi-01"), "/")
    assert res.action == "block" and res.status == 403
    assert ev[-1]["outcome"] == "blocked"


def test_allow_reaches_real_backend(lab):
    router, ev = lab
    res = router.route(flow("f3", "ops-01", "vpi-01"), "/health")
    assert res.action == "allow" and res.status == 200
    assert body_json(res)["svc"] == "real-backend"


def test_decoy_down_fails_closed(lab):
    router, ev = lab
    router.decoy_url = "http://127.0.0.1:1"  # dead
    res = router.route(flow("f4", "attacker-01", "vpi-01"), "/")
    assert res.status == 502
    assert ev[-1]["outcome"] == "backend_error"


def test_redirect_without_decoy_config_denied(lab):
    router, _ = lab
    router.decoy_url = None
    res = router.route(flow("f5", "attacker-01", "vpi-01"), "/")
    assert res.status == 403
    assert res.action == "redirect"


def test_evidence_schema(lab):
    router, ev = lab
    router.route(flow("f6", "attacker-01", "vpi-01"), "/config")
    e = ev[-1]
    assert e["schema"] == "deception-evidence/1"
    assert e["trace_id"] and e["decision_id"] and e["flow_id"]
    assert e["provenance"] == "DEMO"


def test_flow_id_sanitized(lab):
    router, _ = lab
    res = router.route(flow("bad/id:with spaces", "ops-01", "vpi-01"))
    assert res.status == 200
