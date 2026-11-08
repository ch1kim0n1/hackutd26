import json
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from honeypot_service import BAIT, DEVICE_ID, DecoyState, make_server  # noqa: E402


@pytest.fixture()
def decoy():
    state = DecoyState()
    srv = make_server("127.0.0.1", 0, state=state)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}", state
    srv.shutdown()


def get(url, data=None):
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, json.loads(r.read()), dict(r.headers)


def test_decoy_identity(decoy):
    url, _ = decoy
    code, body, _ = get(url + "/")
    assert code == 200
    assert body["device_id"] == DEVICE_ID == "decoy-01"
    assert body["synthetic"] is True
    assert body["trace_id"].startswith("decoy-")


def test_all_bait_endpoints(decoy):
    url, _ = decoy
    for path in BAIT:
        code, body, _ = get(url + path)
        assert code == 200, path
        assert body["synthetic"] is True


def test_unknown_path_logged_404(decoy):
    url, state = decoy
    with pytest.raises(Exception):
        get(url + "/definitely-not-here")
    assert state.connections
    assert state.connections[-1].path == "/definitely-not-here"


def test_connection_logging(decoy):
    url, state = decoy
    get(url + "/login")
    get(url + "/config")
    logs = state.recent()
    assert len(logs) >= 2
    assert logs[-1]["path"] == "/config"
    assert logs[-1]["payload_sha256"]
    assert logs[-1]["client"].startswith("127.")


def test_post_body_hashed(decoy):
    url, state = decoy
    req = urllib.request.Request(url + "/login",
                                 data=b"user=admin&pass=decoy123")
    with urllib.request.urlopen(req, timeout=5) as r:
        r.read()
    log = state.connections[-1]
    assert log.method == "POST"
    assert len(log.payload_sha256) == 16


def test_synthetic_only_no_real_creds(decoy):
    url, _ = decoy
    _, body, _ = get(url + "/config")
    blob = json.dumps(body)
    # no real-looking secrets: decoy markers present
    assert "DECOY" in blob or "decoy" in blob
    assert "SYNTHETIC" in blob


def test_trace_header_returned(decoy):
    url, _ = decoy
    _, _, headers = get(url + "/")
    assert "X-Decoy-Trace" in headers
