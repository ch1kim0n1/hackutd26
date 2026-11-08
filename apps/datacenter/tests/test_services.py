import json
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services"))

import vpi_service  # noqa: E402


@pytest.fixture()
def server(node_id="vpi-compute-01"):
    srv = vpi_service.make_server(node_id, "127.0.0.1", 0)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}", node_id
    srv.shutdown()


def get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, json.loads(r.read())


def test_health(server):
    url, node_id = server
    code, body = get(url + "/health")
    assert code == 200
    assert body["node_id"] == node_id
    assert body["status"] == "ok"
    assert body["synthetic"] is True


def test_metrics_synthetic(server):
    url, _ = server
    _, body = get(url + "/metrics")
    assert body["synthetic"] is True
    assert "cpu_pct" in body and "mem_pct" in body


def test_config_matches_baseline(server):
    url, node_id = server
    _, body = get(url + "/config")
    profile = vpi_service.PROFILES[node_id]
    assert body["config"] == profile.config_baseline
    assert body["baseline_hash"] == profile.baseline_hash


def test_services_list(server):
    url, _ = server
    _, body = get(url + "/services")
    assert body["synthetic"] is True
    assert body["services"]
    assert all("name" in s and "port" in s for s in body["services"])


def test_unknown_node_rejected():
    with pytest.raises(SystemExit):
        vpi_service.make_server("not-a-node", "127.0.0.1", 0)


def test_404(server):
    url, _ = server
    with pytest.raises(Exception):
        get(url + "/nope")


def test_node_isolation():
    """Each node serves only its own profile data."""
    results = {}
    for nid in ("vpi-compute-01", "vpi-network-01", "vpi-sensor-01",
                "vpi-mgmt-01"):
        srv = vpi_service.make_server(nid, "127.0.0.1", 0)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        _, body = get(f"http://127.0.0.1:{port}/health")
        results[nid] = body["node_id"]
        srv.shutdown()
    assert results == {k: k for k in results}


def test_drift_env_override(monkeypatch):
    monkeypatch.setenv("DRIFT_KEY", "ssh_password_auth")
    monkeypatch.setenv("DRIFT_VALUE", "true")
    srv = vpi_service.make_server("vpi-compute-01", "127.0.0.1", 0)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        _, body = get(f"http://127.0.0.1:{port}/config")
        assert body["config"]["ssh_password_auth"] == "true"
    finally:
        srv.shutdown()
