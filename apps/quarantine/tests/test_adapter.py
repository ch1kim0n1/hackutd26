import json
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "quarantine" / "src"))
sys.path.insert(0, str(ROOT / "datacenter" / "services"))

from quarantine import (  # noqa: E402
    APPROVED_ACTION_TYPES,
    ActionNotApproved,
    HealthProbeVerify,
    NodeLabAdapter,
)
import vpi_service  # noqa: E402


@pytest.fixture()
def node():
    srv = vpi_service.make_server("vpi-compute-01", "127.0.0.1", 0)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    yield url
    srv.shutdown()


def urls(node):
    return {"vpi-compute-01": node}


def test_approved_action_isolates(node):
    lab = NodeLabAdapter(urls(node))
    res = lab.apply_isolation("vpi-compute-01", "quarantine_vlan")
    assert res["ok"] is True and res["isolated"] is True
    # health now 503
    req = urllib.request.Request(node + "/health")
    try:
        urllib.request.urlopen(req, timeout=5)
        pytest.fail("expected 503")
    except urllib.error.HTTPError as e:
        assert e.code == 503


def test_unapproved_action_refused(node):
    lab = NodeLabAdapter(urls(node))
    with pytest.raises(ActionNotApproved):
        lab.apply_isolation("vpi-compute-01", "rm_rf_everything")
    with pytest.raises(ActionNotApproved):
        lab.apply_isolation("vpi-compute-01", "shell_exec")


def test_release_restores(node):
    lab = NodeLabAdapter(urls(node))
    lab.apply_isolation("vpi-compute-01", "isolate_endpoint")
    res = lab.remove_isolation("vpi-compute-01", "isolate_endpoint")
    assert res["ok"] and res["isolated"] is False
    with urllib.request.urlopen(node + "/health", timeout=5) as r:
        assert json.loads(r.read())["status"] == "ok"


def test_independent_verify(node):
    lab = NodeLabAdapter(urls(node))
    ver = HealthProbeVerify(urls(node))
    assert ver.target_reachable("vpi-compute-01") is True
    assert ver.isolation_effective("vpi-compute-01", "x") is False
    lab.apply_isolation("vpi-compute-01", "disable_switch_port")
    assert ver.isolation_effective("vpi-compute-01", "disable_switch_port")
    assert ver.target_reachable("vpi-compute-01") is False


def test_unknown_node_fails_closed():
    lab = NodeLabAdapter({})
    res = lab.apply_isolation("ghost-node", "isolate_endpoint")
    assert res["ok"] is False
    ver = HealthProbeVerify({})
    assert ver.target_reachable("ghost-node") is False
    assert ver.isolation_effective("ghost-node", "x") is False


def test_all_approved_types_accepted(node):
    lab = NodeLabAdapter(urls(node))
    for at in APPROVED_ACTION_TYPES:
        res = lab.apply_isolation("vpi-compute-01", at)
        assert res["ok"] is True, at
        lab.remove_isolation("vpi-compute-01", at)


def test_no_shell_surface():
    """Adapter exposes only apply/remove_isolation — no exec/eval."""
    lab = NodeLabAdapter({})
    for forbidden in ("exec", "eval", "run", "shell", "command"):
        assert not hasattr(lab, forbidden)
