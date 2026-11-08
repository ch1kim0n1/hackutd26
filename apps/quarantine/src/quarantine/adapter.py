"""Lab quarantine/mitigation executor adapter (#109).

`NodeLabAdapter` implements the containment-executor LabAdapter protocol
against #101 vpi nodes' /admin/isolate endpoint. Policy-approved action
types only (mirrors module ActionType enum); anything else refused
before any network call. `HealthProbeVerify` is the independent
verifier: it probes /health from a separate vantage and only reports
effective when the node actually returns 503 — never trusts the
adapter's API ack.

Lab scope: HTTP to node admin endpoints on the isolated DC network.
No shell, no arbitrary commands, no credential handling.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

# mirrors spacetimedb ActionType enum — the ONLY approved set
APPROVED_ACTION_TYPES = frozenset({
    "isolate_endpoint",
    "block_ssid",
    "revoke_credential",
    "disable_switch_port",
    "collect_forensics",
    "quarantine_vlan",
})


class ActionNotApproved(PermissionError):
    pass


class NodeLabAdapter:
    """LabAdapter impl: POST /admin/isolate|release on vpi nodes."""

    def __init__(self, node_urls: dict[str, str], timeout_s: float = 5.0):
        """node_urls: node_id -> base URL (e.g. http://vpi-compute-01:8080)."""
        self.node_urls = dict(node_urls)
        self.timeout = timeout_s

    def _post(self, node_id: str, path: str, payload: dict) -> dict:
        base = self.node_urls.get(node_id)
        if base is None:
            return {"ok": False, "error": f"unknown_node:{node_id}"}
        req = urllib.request.Request(
            base.rstrip("/") + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read() or b"{}")
            except Exception:
                return {"ok": False, "error": f"http_{e.code}"}
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return {"ok": False, "error": f"unreachable:{e}"}

    def _check_action(self, action_type: str) -> None:
        if action_type not in APPROVED_ACTION_TYPES:
            raise ActionNotApproved(
                f"action_type {action_type!r} not in approved set")

    def apply_isolation(self, target_id: str, action_type: str) -> dict:
        self._check_action(action_type)
        return self._post(target_id, "/admin/isolate",
                          {"action_type": action_type})

    def remove_isolation(self, target_id: str, action_type: str) -> dict:
        self._check_action(action_type)
        return self._post(target_id, "/admin/release", {})


class HealthProbeVerify:
    """VerifyAdapter impl: independent /health probe.

    isolation_effective == node reports isolated (503 + status field).
    target_reachable == /health returns 200. Probes go over plain HTTP
    GET — a different code path than the adapter's POST, so a lying
    adapter cannot fake verification.
    """

    def __init__(self, node_urls: dict[str, str], timeout_s: float = 5.0):
        self.node_urls = dict(node_urls)
        self.timeout = timeout_s

    def _get_health(self, target_id: str):
        base = self.node_urls.get(target_id)
        if base is None:
            return None, None
        req = urllib.request.Request(base.rstrip("/") + "/health")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"{}")
            except Exception:
                return e.code, {}
        except (urllib.error.URLError, TimeoutError, OSError):
            return None, None

    def target_reachable(self, target_id: str) -> bool:
        status, _ = self._get_health(target_id)
        return status == 200

    def isolation_effective(self, target_id: str,
                            action_type: str) -> bool:
        status, body = self._get_health(target_id)
        return status == 503 and body.get("status") == "isolated"
