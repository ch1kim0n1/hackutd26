"""Decoy honeypot service (#107).

Standalone service identity (device_id=decoy-01) exposing fake HTTP
endpoints with SYNTHETIC credentials/data only. Every connection logged
with trace_id + client addr + payload hash — evidence for incident
records. Resource-limited, loopback/LAN only, no real creds/data.

Future rover-host adapter boundary: the same DecoyHandler runs on the
rover's interface when #108 deception routing lands; until then this is
a lab service, honestly labeled.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEVICE_ID = "decoy-01"

# synthetic bait — obviously fake, never real credentials
BAIT = {
    "/": {"service": "MERIDIAN-PRINTER-ADMIN", "version": "fake-1.0",
          "note": "SYNTHETIC decoy - no real service"},
    "/login": {"form": "user=admin&pass=decoy123",
               "banner": "MERIDIAN INTERNAL - unauthorized access logged"},
    "/config": {"admin_password": "CHANGE-ME-DECOY",
                "snmp_community": "public-decoy",
                "note": "SYNTHETIC"},
    "/firmware": {"file": "decoy-fw-9.9.bin", "size": 0,
                  "note": "SYNTHETIC placeholder"},
}


@dataclass
class ConnectionLog:
    trace_id: str
    client: str
    method: str
    path: str
    at: float
    payload_sha256: str = ""
    headers: dict = field(default_factory=dict)


class DecoyState:
    def __init__(self):
        self.connections: list[ConnectionLog] = []
        self.blocked: list[str] = []

    def record(self, client: str, method: str, path: str,
               body: bytes = b"", headers: dict | None = None) -> ConnectionLog:
        log = ConnectionLog(
            trace_id=f"decoy-{uuid.uuid4().hex[:10]}",
            client=client, method=method, path=path, at=time.time(),
            payload_sha256=hashlib.sha256(body).hexdigest()[:16],
            headers={k: v for k, v in (headers or {}).items()
                     if k.lower() in ("user-agent", "referer")},
        )
        self.connections.append(log)
        return log

    def recent(self, n: int = 50) -> list[dict]:
        return [vars(c) for c in self.connections[-n:]]


class DecoyHandler(BaseHTTPRequestHandler):
    state: DecoyState = DecoyState()

    def _handle(self, method: str) -> None:
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""
        log = self.state.record(
            self.client_address[0], method, self.path,
            body=body,
            headers={k: self.headers.get(k, "") for k in
                     ("User-Agent", "Referer")})
        route = self.path.split("?")[0]
        payload = BAIT.get(route)
        if payload is None:
            # unknown path -> tarpit-style generic response, still logged
            payload = {"error": "not_found", "trace_id": log.trace_id}
            code = 404
        else:
            code = 200
        out = json.dumps({**payload, "trace_id": log.trace_id,
                          "device_id": DEVICE_ID,
                          "synthetic": True},
                         separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Decoy-Trace", log.trace_id)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):  # noqa: N802
        self._handle("GET")

    def do_POST(self):  # noqa: N802
        self._handle("POST")

    def log_message(self, *args):
        pass


def make_server(host: str = "127.0.0.1", port: int = 0,
                state: DecoyState | None = None) -> ThreadingHTTPServer:
    DecoyHandler.state = state or DecoyState()
    return ThreadingHTTPServer((host, port), DecoyHandler)


def main() -> None:
    import os
    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("BIND", "127.0.0.1")
    srv = make_server(host, port)
    print(f"honeypot decoy {DEVICE_ID} on {host}:{port} (synthetic)",
          flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
