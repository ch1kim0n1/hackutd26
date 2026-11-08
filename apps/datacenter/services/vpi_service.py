"""Mock virtual-Pi service (#101).

Per-node HTTP stand-in with synthetic data only. Endpoints:
  GET /health    -> liveness + node identity
  GET /metrics   -> synthetic telemetry series
  GET /config    -> live config snapshot (posture engine input)
  GET /services  -> declared service list

NODE_ID env selects the profile from datacenter.nodes.PI_PROFILES.
Read-only; no state mutation, no credentials, no real data.
"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from datacenter.nodes import PI_PROFILES  # noqa: E402

PROFILES = {p.node_id: p for p in PI_PROFILES}

# deterministic synthetic metrics per node (seeded by node index)
_BASE_METRICS = {
    "vpi-compute-01": {"cpu_pct": 34, "mem_pct": 61, "load1": 0.42},
    "vpi-network-01": {"cpu_pct": 12, "mem_pct": 28, "load1": 0.08},
    "vpi-sensor-01": {"cpu_pct": 8, "mem_pct": 19, "load1": 0.03},
    "vpi-mgmt-01": {"cpu_pct": 5, "mem_pct": 15, "load1": 0.02},
}


def _config_snapshot(profile) -> dict:
    """Live config = baseline + optional DRIFT_KEY/DRIFT_VALUE env override
    (lets tests/demo simulate posture drift without code changes)."""
    cfg = dict(profile.config_baseline)
    dk = os.environ.get("DRIFT_KEY")
    if dk:
        cfg[dk] = os.environ.get("DRIFT_VALUE", "drifted")
    return cfg


class Handler(BaseHTTPRequestHandler):
    profile = None  # set by server factory

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        p = self.profile
        routes = {
            "/health": lambda: {
                "status": "ok", "node_id": p.node_id,
                "role": p.role.value, "zone_id": p.zone_id,
                "synthetic": True,
            },
            "/metrics": lambda: {
                "node_id": p.node_id, "synthetic": True,
                **_BASE_METRICS.get(p.node_id, {}),
            },
            "/config": lambda: {
                "node_id": p.node_id, "synthetic": True,
                "config": _config_snapshot(p),
                "baseline_hash": p.baseline_hash,
            },
            "/services": lambda: {
                "node_id": p.node_id, "synthetic": True,
                "services": [
                    {"name": s.name, "port": s.port,
                     "protocol": s.protocol, "version": s.version}
                    for s in p.services
                ],
            },
        }
        handler = routes.get(self.path.split("?")[0])
        if handler:
            self._json(200, handler())
        else:
            self._json(404, {"error": "not_found", "synthetic": True})

    def log_message(self, *args):  # quiet
        pass


def make_server(node_id: str, host: str = "0.0.0.0", port: int = 8080):
    profile = PROFILES.get(node_id)
    if profile is None:
        raise SystemExit(f"unknown NODE_ID {node_id!r}; "
                         f"choices: {sorted(PROFILES)}")

    class Bound(Handler):
        pass
    Bound.profile = profile
    return ThreadingHTTPServer((host, port), Bound)


def main() -> None:
    node_id = os.environ.get("NODE_ID", "vpi-compute-01")
    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("BIND", "0.0.0.0")
    srv = make_server(node_id, host, port)
    print(f"vpi-service {node_id} on {host}:{port} (synthetic)", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
