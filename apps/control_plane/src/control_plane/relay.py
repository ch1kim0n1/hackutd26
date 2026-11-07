"""Outbound-only lab->management observation relay (docs/06 R01).

- Devices authenticate with scoped, expiring, revocable tokens —
  telemetry is DATA, never instructions.
- Replay protection: event_id dedup + per-device seq monotonicity.
- Rate/size limits per docs/08 (oversized/malformed fail safely).
- Fail closed: if identity store, policy engine or audit sink is
  unavailable, WRITES are denied; read-only cached state may continue
  marked stale — never actuation."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field

MAX_PACKET_BYTES = 8192
MAX_EVENTS_PER_WINDOW = 60
RATE_WINDOW_S = 60.0


class RelayUnavailable(RuntimeError):
    """Identity/policy/audit dependency down -> fail closed."""


@dataclass
class DeviceToken:
    device_id: str
    scope: str                    # e.g. "telemetry:ingest"
    secret: bytes
    expires_at: float
    revoked: bool = False


@dataclass
class RelayResult:
    ok: bool
    reason: str
    event_id: str = ""
    stale: bool = False


class LabRelay:
    def __init__(self, tokens: dict[str, DeviceToken] | None = None,
                 clock=time.time):
        self.tokens = tokens or {}
        self.clock = clock
        self.seen_event_ids: set[str] = set()
        self.seen_seq: dict[str, int] = {}
        self.accepted: list[dict] = []
        self.rejected: list[tuple[str, str]] = []
        self._rate: dict[str, list[float]] = {}
        # dependency health — when False, writes fail closed
        self.identity_ok = True
        self.policy_ok = True
        self.audit_ok = True

    # ---------------- auth ----------------
    def issue_token(self, device_id: str, scope: str, secret: bytes,
                    ttl_s: float = 86400) -> DeviceToken:
        t = DeviceToken(device_id=device_id, scope=scope, secret=secret,
                        expires_at=self.clock() + ttl_s)
        self.tokens[device_id] = t
        return t

    def revoke(self, device_id: str) -> None:
        if device_id in self.tokens:
            self.tokens[device_id].revoked = True

    def _authenticate(self, device_id: str, signature: str,
                      body: bytes) -> tuple[bool, str]:
        if not self.identity_ok:
            return False, "identity store unavailable — fail closed"
        tok = self.tokens.get(device_id)
        if tok is None:
            return False, "unknown device"
        if tok.revoked:
            return False, "token revoked"
        if self.clock() > tok.expires_at:
            return False, "token expired"
        expected = hmac.new(tok.secret, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return False, "bad signature"
        return True, "ok"

    # ---------------- ingest ----------------
    def ingest(self, raw: dict) -> RelayResult:
        """Validate + accept one canonical event dict (docs/04 shape)."""
        # fail-closed dependency check BEFORE any write path
        if not (self.identity_ok and self.policy_ok and self.audit_ok):
            return RelayResult(False, "relay dependency down — writes denied",
                               stale=not self.audit_ok)
        device_id = str(raw.get("device_id", ""))
        signature = str(raw.get("signature", ""))
        body = json.dumps({k: v for k, v in raw.items()
                           if k != "signature"},
                          sort_keys=True, separators=(",", ":")).encode()
        ok, reason = self._authenticate(device_id, signature, body)
        if not ok:
            self.rejected.append((device_id, reason))
            return RelayResult(False, reason)
        # schema-lite checks
        if raw.get("schema_version") != 1:
            return self._rej(device_id, "bad_schema_version")
        if not raw.get("kind") or not raw.get("observed_at"):
            return self._rej(device_id, "missing kind/observed_at")
        event_id = str(raw.get("event_id", ""))
        seq = int(raw.get("seq", 0))
        if event_id and event_id in self.seen_event_ids:
            return self._rej(device_id, "duplicate event_id (replay)")
        if seq <= self.seen_seq.get(device_id, 0):
            return self._rej(device_id, "stale/replayed seq")
        if len(body) > MAX_PACKET_BYTES:
            return self._rej(device_id, "oversized packet")
        # rate limit
        now = self.clock()
        wins = [t for t in self._rate.get(device_id, [])
                if now - t < RATE_WINDOW_S]
        self._rate[device_id] = wins
        if len(wins) >= MAX_EVENTS_PER_WINDOW:
            return self._rej(device_id, "rate limit exceeded")
        # accept
        self._rate[device_id].append(now)
        self.seen_event_ids.add(event_id)
        self.seen_seq[device_id] = seq
        self.accepted.append(raw)
        return RelayResult(True, "accepted", event_id)

    def _rej(self, device_id: str, reason: str) -> RelayResult:
        self.rejected.append((device_id, reason))
        return RelayResult(False, reason)
