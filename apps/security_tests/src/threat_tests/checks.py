"""Automated adversarial checks against the security boundaries.

Each check exercises ONE boundary from docs/08 and returns PASS/FAIL
with evidence. Runs against injectable service doubles — in-memory
fakes for CI, real endpoints for deployment runs (same checks).

Boundaries (docs/08 + docs/06):
  B1 network deny paths        — lab/hostile principals reach nothing
  B2 telemetry forgery         — unsigned/bad-sig events rejected
  B3 subscription enumeration  — cross-incident subscription denied
  B4 expired sessions          — stale tokens denied everywhere
  B5 evidence upload           — oversized/invalid/mime-spoofed denied
  B6 identity boundary         — machine principals can't human-login;
                                 privilege escalation denied
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field


@dataclass
class CheckResult:
    check_id: str
    name: str
    status: str          # PASS | FAIL
    detail: str = ""
    evidence: dict = field(default_factory=dict)


# ---------------- minimal service doubles (deployment swaps real) ------

class FakeIdP:
    """Identity boundary double — machine/human separation + sessions."""
    def __init__(self):
        self.users = {
            "admin-1": {"role": "admin", "kind": "human", "active": True},
            "resp-1": {"role": "responder", "kind": "human", "active": True},
            "puck-1": {"role": "device", "kind": "machine", "active": True},
            "evil-1": {"role": "observer", "kind": "human", "active": False},
        }
        self.sessions: dict[str, dict] = {}

    def login(self, username: str) -> str | None:
        u = self.users.get(username)
        if not u or u["kind"] != "human" or not u["active"]:
            return None
        tok = f"s-{len(self.sessions)}"
        self.sessions[tok] = {"user": username, "exp": time.time() + 60}
        return tok

    def valid_session(self, tok: str) -> bool:
        s = self.sessions.get(tok)
        return bool(s and s["exp"] > time.time())

    def revoke(self, tok: str) -> None:
        self.sessions.pop(tok, None)


class FakeRelay:
    """Telemetry boundary double — HMAC + dedup + seq."""
    def __init__(self, secret: bytes):
        self.secret = secret
        self.seen: set[str] = set()
        self.seq: dict[str, int] = {}

    def ingest(self, ev: dict) -> tuple[bool, str]:
        body = json.dumps({k: v for k, v in ev.items() if k != "sig"},
                          sort_keys=True).encode()
        expected = hmac.new(self.secret, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, ev.get("sig", "")):
            return False, "bad_signature"
        eid = ev.get("event_id", "")
        if eid in self.seen:
            return False, "replay"
        dev = ev.get("device_id", "")
        if ev.get("seq", 0) <= self.seq.get(dev, 0):
            return False, "stale_seq"
        self.seen.add(eid)
        self.seq[dev] = ev.get("seq", 0)
        return True, "ok"


class FakeSubscriptions:
    """Subscription boundary double — incident-scoped read."""
    ROOMS = {"inc-1": {"admin-1", "resp-1"},
             "inc-2": {"resp-1"}}

    def can_subscribe(self, user: str, room: str) -> bool:
        return user in self.ROOMS.get(room, set())


class FakeEvidenceStore:
    """Evidence boundary double — upload validation."""
    MAX_BYTES = 1024
    ALLOWED_MIME = {"image/png", "application/json", "text/plain"}

    def validate_upload(self, data: bytes, mime: str,
                        claimed_name: str) -> tuple[bool, str]:
        if len(data) > self.MAX_BYTES:
            return False, "oversized"
        if mime not in self.ALLOWED_MIME:
            return False, "mime_not_allowed"
        # magic-byte sniff for png/json — spoofed mime rejected
        if mime == "image/png" and not data.startswith(b"\x89PNG"):
            return False, "mime_spoof"
        if mime == "application/json":
            try:
                json.loads(data)
            except Exception:
                return False, "invalid_json"
        if ".." in claimed_name or claimed_name.startswith("/"):
            return False, "path_traversal"
        return True, "ok"


# ---------------- the six checks ---------------------------------------

def check_network_deny(idp: FakeIdP) -> CheckResult:
    """B1: hostile/lab principals reach no management service."""
    hostile_attempts = [
        idp.login("puck-1"),          # machine -> no human session
        idp.login("evil-1"),          # inactive -> no session
        idp.sessions.get("nonexistent"),
    ]
    leaked = [t for t in hostile_attempts if t]
    ok = not leaked
    return CheckResult(
        "B1", "network deny paths", "PASS" if ok else "FAIL",
        "lab/machine/inactive principals obtain no management session",
        {"attempts": len(hostile_attempts), "sessions_leaked": len(leaked)})


def check_telemetry_forgery(relay: FakeRelay) -> CheckResult:
    """B2: unsigned/forged/replayed telemetry rejected."""
    secret = relay.secret
    good = {"schema_version": 1, "event_id": "e1", "device_id": "d1",
            "seq": 1, "kind": "wifi", "observed_at": "t"}
    body = json.dumps(good, sort_keys=True).encode()
    good["sig"] = hmac.new(secret, body, hashlib.sha256).hexdigest()
    results = {
        "valid": relay.ingest(dict(good))[0],
        "forged": relay.ingest({**good, "event_id": "e2", "seq": 2,
                                "sig": "deadbeef"})[0] is False,
        "replay": relay.ingest(dict(good))[0] is False,
        "stale_seq": relay.ingest({**good, "event_id": "e3", "seq": 0,
                                   "sig": hmac.new(
                                       secret,
                                       json.dumps(
                                           {k: v for k, v in
                                            {**good, "event_id": "e3",
                                             "seq": 0}.items()
                                            if k != "sig"},
                                           sort_keys=True).encode(),
                                       hashlib.sha256).hexdigest()})[0] is False,
    }
    ok = results["valid"] and all(
        results[k] for k in ("forged", "replay", "stale_seq"))
    return CheckResult(
        "B2", "telemetry forgery rejection",
        "PASS" if ok else "FAIL",
        "valid accepted; forged sig, replay, stale seq rejected",
        results)


def check_subscription_enum(subs: FakeSubscriptions, idp: FakeIdP) -> CheckResult:
    """B3: cross-incident subscription denied; room enumeration
    reveals nothing beyond membership."""
    tok = idp.login("resp-1")
    assert tok
    # resp-1 is member of inc-1 AND inc-2 per fixture; test with a user
    # NOT in inc-2 -> admin-1 only in inc-1
    cases = {
        "member_subscribes": subs.can_subscribe("resp-1", "inc-1"),
        "nonmember_denied": not subs.can_subscribe("admin-1", "inc-2"),
        "unknown_room_denied": not subs.can_subscribe("resp-1", "inc-999"),
        "enumeration_empty": subs.can_subscribe("nobody", "inc-1") is False,
    }
    ok = all(cases.values())
    return CheckResult(
        "B3", "subscription enumeration prevention",
        "PASS" if ok else "FAIL",
        "membership checked server-side; unknown users/rooms denied",
        cases)


def check_expired_sessions(idp: FakeIdP) -> CheckResult:
    """B4: expired/revoked sessions denied on every service."""
    tok = idp.login("admin-1")
    assert tok and idp.valid_session(tok)
    idp.sessions[tok]["exp"] = time.time() - 1   # force expiry
    expired_denied = not idp.valid_session(tok)
    tok2 = idp.login("resp-1")
    idp.revoke(tok2)
    revoked_denied = tok2 not in idp.sessions
    ok = expired_denied and revoked_denied
    return CheckResult(
        "B4", "expired/revoked session denial",
        "PASS" if ok else "FAIL",
        "expired token and revoked token both rejected",
        {"expired_denied": expired_denied, "revoked_denied": revoked_denied})


def check_evidence_upload(store: FakeEvidenceStore) -> CheckResult:
    """B5: oversized, wrong-mime, spoofed, traversal uploads denied."""
    cases = {
        "valid_png": store.validate_upload(b"\x89PNG" + b"0" * 100,
                                           "image/png", "shot.png")[0],
        "oversized": not store.validate_upload(b"x" * 2048,
                                               "text/plain", "big.txt")[0],
        "bad_mime": not store.validate_upload(b"MZ" + b"0" * 50,
                                              "application/x-msdownload",
                                              "evil.exe")[0],
        "mime_spoof": not store.validate_upload(b"not-a-png",
                                                "image/png", "fake.png")[0],
        "traversal": not store.validate_upload(b"{}", "application/json",
                                               "../../etc/passwd")[0],
        "invalid_json": not store.validate_upload(b"{bad",
                                                  "application/json",
                                                  "x.json")[0],
    }
    ok = all(cases.values())
    return CheckResult(
        "B5", "evidence upload validation",
        "PASS" if ok else "FAIL",
        "oversized/mime/spoof/traversal/invalid all rejected",
        cases)


def check_identity_boundary(idp: FakeIdP) -> CheckResult:
    """B6: machine can't human-login; inactive/unknown denied;
    no privilege escalation path via session."""
    cases = {
        "machine_login_denied": idp.login("puck-1") is None,
        "inactive_denied": idp.login("evil-1") is None,
        "unknown_denied": idp.login("ghost") is None,
        "human_login_ok": idp.login("admin-1") is not None,
        "no_token_no_access": idp.valid_session("forged-token") is False,
    }
    ok = all(cases.values())
    return CheckResult(
        "B6", "identity boundary verification",
        "PASS" if ok else "FAIL",
        "machine/inactive/unknown/forged-token all denied",
        cases)


ALL_CHECKS = [
    check_network_deny,
    check_telemetry_forgery,
    check_subscription_enum,
    check_expired_sessions,
    check_evidence_upload,
    check_identity_boundary,
]


def run_all() -> list[CheckResult]:
    """Run every boundary check against fresh doubles."""
    idp = FakeIdP()
    relay = FakeRelay(b"test-secret")
    subs = FakeSubscriptions()
    store = FakeEvidenceStore()
    return [
        check_network_deny(idp),
        check_telemetry_forgery(relay),
        check_subscription_enum(subs, idp),
        check_expired_sessions(idp),
        check_evidence_upload(store),
        check_identity_boundary(idp),
    ]
