import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
APPS = Path(__file__).resolve().parents[2]
DC = APPS / "datacenter"
sys.path.insert(0, str(DC / "src"))
sys.path.insert(0, str(DC / "services"))
GW = APPS / "defense" / "gateway" / "src"
sys.path.insert(0, str(GW))

import vpi_service  # noqa: E402
from defense_gateway import DecisionEngine  # noqa: E402
from traffic_path.proxy import PathProxy, lab_policy  # noqa: E402


@pytest.fixture()
def backend():
    srv = vpi_service.make_server("vpi-compute-01", "127.0.0.1", 0)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


def make_proxy(backend_url, **kw):
    engine = DecisionEngine(lab_policy())
    return PathProxy(engine=engine, backend_url=backend_url, **kw)


def test_allowed_request_reaches_backend(backend):
    proxy = make_proxy(backend)
    r = proxy.forward("/health", src_node="ops-01", trace_id="t1")
    assert r["status"] == 200
    assert r["body"]["node_id"] == "vpi-compute-01"
    assert r["decision"]["decision"] == "allow"
    assert r["decision"]["enforcement"] == "REAL"


def test_blocked_source_never_touches_backend(backend):
    proxy = make_proxy(backend)
    r = proxy.forward("/config", src_node="attacker-01", trace_id="t2")
    assert r["status"] == 403
    assert r["body"]["error"] == "blocked_by_policy"
    assert r["decision"]["decision"] == "block"
    # backend NOT contacted: no config data leaked
    assert "config" not in r["body"]


def test_every_decision_logged(backend):
    proxy = make_proxy(backend)
    proxy.forward("/health", src_node="ops-01", trace_id="a")
    proxy.forward("/metrics", src_node="attacker-01", trace_id="b")
    proxy.forward("/services", src_node="ops-02", trace_id="c")
    assert len(proxy.decisions) == 3
    assert [d["decision"] for d in proxy.decisions] == \
        ["allow", "block", "allow"]
    assert all(d["enforcement"] == "REAL" for d in proxy.decisions)


def test_redirect_to_sink(backend):
    # policy that redirects attacker to sink endpoint
    from defense_gateway import (DefaultAction, FlowDecisionKind,
                                 FlowEndpoint, FlowMatch, FlowPolicy,
                                 FlowRule)
    policy = FlowPolicy(
        policy_id="redir-v1",
        rules=[FlowRule(
            rule_id="redir-attacker",
            match=FlowMatch(src_node="attacker-01"),
            action=FlowDecisionKind.REDIRECT,
            redirect_to=FlowEndpoint(node_id="sink-01", service="http"),
            reason="deceive attacker")],
        default_action=DefaultAction.MONITOR)
    proxy = PathProxy(engine=DecisionEngine(policy),
                      backend_url=backend, sink_url=None)
    r = proxy.forward("/health", src_node="attacker-01", trace_id="r1")
    assert r["decision"]["decision"] == "redirect"
    assert r["status"] in (200, 302)


def test_unreachable_backend_502(backend):
    proxy = make_proxy("http://127.0.0.1:1")  # dead
    r = proxy.forward("/health", src_node="ops-01")
    assert r["status"] == 502
    assert r["decision"]["decision"] == "allow"  # decision made, upstream failed


def test_metrics_endpoint_real_data(backend):
    proxy = make_proxy(backend)
    r = proxy.forward("/metrics", src_node="ops-01")
    assert r["status"] == 200
    assert "cpu_pct" in r["body"]
    assert r["body"]["synthetic"] is True
