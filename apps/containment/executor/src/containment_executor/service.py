"""HTTP front for the lab executor — bridges the SpacetimeDB outbox
gateway webhook (services/gateway -> EXECUTOR_WEBHOOK_URL) into the
approval-bound executor with independent verification.

Wire contract (gateway POSTs the module's payloadJson verbatim):
  {schema_version, action_id, incident_id, type, target_id,
   fingerprint, approval_id}

Response mapping (honest — docs/08 threat 3):
  200  record.state == VERIFIED   -> gateway records outcome 'succeeded'
  502  anything else              -> gateway records outcome 'failed'
  400  malformed payload          -> gateway records outcome 'failed'

Redelivery of an already-VERIFIED action returns 200 (idempotent).
The module's approval/expiry enforcement already happened upstream; this
service adds a short execution TTL as a second guard.

Run:  python -m containment_executor.service
Env:  EXECUTOR_PORT (8082), EXECUTOR_TOKEN (bearer, optional in lab),
      EXECUTOR_ACTION_TTL_S (300), EXECUTOR_LIE_ABOUT_SUCCESS=1,
      EXECUTOR_FAIL_APPLY=1  (test hooks for the honesty paths)
"""
from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .adapters import MockLabAdapter, MockVerifyAdapter
from .executor import Executor
from .models import OutboxItem
from .outbox import Outbox

REQUIRED_FIELDS = ("action_id", "incident_id", "type", "target_id",
                   "fingerprint", "approval_id")


def item_from_payload(doc: dict, ttl_s: float) -> OutboxItem:
    missing = [f for f in REQUIRED_FIELDS if not doc.get(f)]
    if doc.get("schema_version") != 1:
        missing.append("schema_version")
    if missing:
        raise ValueError(f"missing/invalid fields: {missing}")
    return OutboxItem(
        action_id=str(doc["action_id"]),
        incident_id=str(doc["incident_id"]),
        action_type=str(doc["type"]),
        target_id=str(doc["target_id"]),
        reason="gateway outbox delivery",
        approved_by=f"approval:{doc['approval_id']}",
        approval_id=str(doc["approval_id"]),
        expires_at=time.time() + ttl_s,
        fingerprint=str(doc["fingerprint"]),
        payload={k: v for k, v in doc.items()
                 if k not in REQUIRED_FIELDS and k != "schema_version"},
    )


class ExecutorService:
    """Thread-safe wrapper: one Outbox+Executor, serialized run_once."""

    def __init__(self, lab=None, verify=None, ttl_s: float = 300.0):
        self.lab = lab or MockLabAdapter()
        self.verify = verify or MockVerifyAdapter(self.lab)
        self.outbox = Outbox()
        self.executor = Executor(self.outbox, self.lab, self.verify)
        self.ttl_s = ttl_s
        # retain delivered items so /revert can rebuild context after
        # outbox.complete() pops them from the pending queue
        self._items: dict[str, OutboxItem] = {}
        self._lock = threading.Lock()

    def execute(self, doc: dict):
        """-> (http_status, record_dict)."""
        item = item_from_payload(doc, self.ttl_s)
        with self._lock:
            existing = self.outbox.records.get(item.action_id)
            if existing is not None and existing.state.value == "verified":
                return 200, self._body(existing)
            if existing is None or existing.state.value == "queued":
                self.outbox.deliver(item)
                self._items[item.action_id] = item
                self.executor.run_once()
            rec = self.outbox.records.get(item.action_id)
        if rec is None:
            return 500, {"error": "no execution record"}
        return (200 if rec.state.value == "verified" else 502), \
            self._body(rec)

    @staticmethod
    def _body(rec) -> dict:
        return {
            "action_id": rec.action_id,
            "state": rec.state.value,
            "verification": rec.verification,
            "error": rec.error,
            "states": [h["state"] for h in rec.states_history],
        }

    def revert(self, action_id: str):
        item = self._items.get(action_id)
        if item is None:
            return 404, {"error": "unknown action_id"}
        with self._lock:
            rec = self.executor.revert(item)
        if rec is None:
            return 404, {"error": "no execution record"}
        return 200, {"action_id": rec.action_id, "state": rec.state.value,
                     "verification": rec.verification}

    def health(self) -> dict:
        with self._lock:
            return {
                "ok": True,
                "pending": len(self.outbox.pending()),
                "records": len(self.outbox.records),
            }


def make_handler(service: ExecutorService, token: str):
    class Handler(BaseHTTPRequestHandler):
        def _auth_ok(self) -> bool:
            if not token:
                return True
            return self.headers.get("authorization") == f"Bearer {token}"

        def _send(self, code: int, obj: dict) -> None:
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path == "/healthz":
                self._send(200, service.health())
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            if not self._auth_ok():
                self._send(401, {"error": "unauthorized"})
                return
            if self.path == "/execute":
                self._handle_execute()
            elif self.path == "/revert":
                self._handle_revert()
            else:
                self._send(404, {"error": "not found"})

        def _read_json(self):
            n = int(self.headers.get("content-length") or 0)
            if n <= 0 or n > 64 * 1024:
                return None
            try:
                return json.loads(self.rfile.read(n))
            except (ValueError, UnicodeDecodeError):
                return None

        def _handle_execute(self):
            doc = self._read_json()
            if not isinstance(doc, dict):
                self._send(400, {"error": "invalid json"})
                return
            try:
                code, body = service.execute(doc)
            except ValueError as e:
                self._send(400, {"error": str(e)})
                return
            self._send(code, body)

        def _handle_revert(self):
            doc = self._read_json()
            if not isinstance(doc, dict) or not doc.get("action_id"):
                self._send(400, {"error": "action_id required"})
                return
            code, body = service.revert(str(doc["action_id"]))
            self._send(code, body)

        def log_message(self, fmt, *args):  # quiet default logging
            pass

    return Handler


def main() -> None:
    port = int(os.environ.get("EXECUTOR_PORT", "8082"))
    token = os.environ.get("EXECUTOR_TOKEN", "")
    ttl = float(os.environ.get("EXECUTOR_ACTION_TTL_S", "300"))
    lab = MockLabAdapter(
        fail_apply=os.environ.get("EXECUTOR_FAIL_APPLY") == "1",
        lie_about_success=os.environ.get("EXECUTOR_LIE_ABOUT_SUCCESS") == "1",
    )
    service = ExecutorService(lab=lab, ttl_s=ttl)
    # Loopback default — set EXECUTOR_BIND=0.0.0.0 only when a remote
    # gateway must reach the service (e.g. inside a compose network).
    bind = os.environ.get("EXECUTOR_BIND", "127.0.0.1")
    server = ThreadingHTTPServer((bind, port),
                                 make_handler(service, token))
    print(f"containment-executor-service on {bind}:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
