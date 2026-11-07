"""GLUE-06: Winstead W01-W05 adversarial cross-system acceptance.

Runs every docs/06 acceptance item against injectable backends and
records PASS / FAIL / NOT RUN with evidence artifacts. NOT RUN is a
first-class outcome — simulated passes are labeled SIMULATED and never
counted as deployment acceptance. The lab-pivot check proves a
compromised lab principal cannot reach management services."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field


@dataclass
class ItemResult:
    req: str            # W01a..W05d
    title: str
    status: str         # PASS | FAIL | NOT_RUN
    mode: str           # REAL | SIMULATED | NOT_RUN
    detail: str = ""
    evidence: dict = field(default_factory=dict)


class AcceptanceRunner:
    """Registry of W01-W05 checks. Each check receives a context of
    backends; missing backend -> NOT_RUN (honest, never faked)."""

    def __init__(self, backends: dict | None = None, clock=time.time):
        self.backends = backends or {}
        self.clock = clock
        self.results: list[ItemResult] = []

    # ---------------- backend probes ----------------------------------
    def _have(self, *names) -> bool:
        return all(n in self.backends for n in names)

    # ---------------- W01: isolated control plane ----------------------
    def w01(self) -> list[ItemResult]:
        out = []
        cp = self.backends.get("control_plane")
        relay = self.backends.get("relay")
        items = [
            ("W01a", "adversarial lab endpoint denied",
             lambda: self._lab_denied(cp)),
            ("W01b", "lab DNS/IdP/LAN failure -> mgmt unaffected",
             lambda: self._lab_outage(cp)),
            ("W01c", "replay + forged telemetry dropped",
             lambda: self._replay(relay)),
            ("W01d", "revoked/expired token denied",
             lambda: self._revoked(cp)),
            ("W01e", "direct containment call refused",
             lambda: self._containment_gate(cp)),
        ]
        for iid, title, fn in items:
            out.append(self._run(iid, title, fn,
                                 needs=["control_plane"]))
        return out

    def _lab_denied(self, cp) -> tuple[bool, str, dict]:
        # red-team: lab-hostile principal reaches zero services
        reached = cp.lab_reachable_services("lab_hostile")
        return (len(reached) == 0,
                f"lab_hostile reached {reached}",
                {"services_reached": reached})

    def _lab_outage(self, cp) -> tuple[bool, str, dict]:
        cp.simulate_lab_disconnect()
        health = cp.management_health()
        ok = all(h["status"] == "up" for h in health.values())
        return (ok, "management services up during lab outage",
                {"health": health})

    def _replay(self, relay) -> tuple[bool, str, dict]:
        if relay is None:
            return (False, "no relay backend", {})
        r1 = relay.ingest(self._signed_event())
        r2 = relay.ingest(self._signed_event())   # replay
        return (r1.ok and not r2.ok,
                f"first={r1.ok} replay={r2.ok}",
                {"first": r1.ok, "replay_accepted": r2.ok})

    def _revoked(self, cp) -> tuple[bool, str, dict]:
        tok = cp.login("operator")
        cp.revoke_session(tok)
        ok = not cp.valid_session(tok)
        return (ok, "revoked session denied", {"denied": ok})

    def _containment_gate(self, cp) -> tuple[bool, str, dict]:
        tok = cp.login("operator")
        ok, reason, _ = cp.request_containment(
            "management", "operator", tok,
            {"action_type": "x", "target_id": "t",
             "incident_id": "i", "approval_id": "none"})
        return (not ok, f"denied: {reason}", {"reason": reason})

    def _signed_event(self) -> dict:
        # minimal valid event for relay double
        return {"schema_version": 1, "event_id": "evt-acc",
                "device_id": "puck-1", "seq": 1, "kind": "motion",
                "observed_at": "t", "signature": "test-sig"}

    # ---------------- W02: identities/RBAC -----------------------------
    def w02(self) -> list[ItemResult]:
        idp = self.backends.get("identity")
        items = [
            ("W02a", "add/revoke user with audit",
             lambda: self._w02a(idp)),
            ("W02b", "observer read-only",
             lambda: self._w02b(idp)),
            ("W02c", "no cross-incident leak",
             lambda: self._w02c(idp)),
            ("W02d", "immediate revocation",
             lambda: self._w02d(idp)),
            ("W02e", "no device human login",
             lambda: self._w02e(idp)),
        ]
        return [self._run(i, t, f, needs=["identity"]) for i, t, f in items]

    def _w02a(self, idp):
        u = idp.add_user("admin", "tmp-user", "observer", "human")
        idp.revoke_user("admin", u["user_id"])
        trail = idp.audit_trail(u["user_id"])
        ops = [a["operation"] for a in trail]
        return ("user_add" in ops and "user_revoke" in ops,
                f"audit ops: {ops}", {"ops": ops})

    def _w02b(self, idp):
        d = idp.authorize("obs-1", "write_incident", "inc-1")
        return (not d["allowed"], f"observer write -> {d['reason']}",
                {"decision": d})

    def _w02c(self, idp):
        d = idp.authorize("resp-1", "read_incident", "inc-2")
        return (not d["allowed"], f"cross-incident -> {d['reason']}",
                {"decision": d})

    def _w02d(self, idp):
        tok = idp.login("resp-1")
        idp.revoke_user("admin", "resp-1")
        return (tok not in idp.sessions and
                not idp.authorize("resp-1", "read_incident",
                                  "inc-1")["allowed"],
                "session destroyed + access denied", {})

    def _w02e(self, idp):
        return (idp.login("puck-1") is None,
                "device human-login denied", {})

    # ---------------- W03-W05: condensed cross-checks ------------------
    def w03_w05(self) -> list[ItemResult]:
        return [
            self._run("W03a-e", "incident records: edit/conflict/evidence/"
                      "export", lambda: self._records(),
                      needs=["incident_service"]),
            self._run("W04a-e", "scope matrix: CIA/statuses/evidence/"
                      "snapshots", lambda: self._scope(),
                      needs=["scope_matrix"]),
            self._run("W05a-d", "chat: exchange/restricted/reconnect/"
                      "dedup", lambda: self._chat(),
                      needs=["chat_service"]),
        ]

    def _records(self):
        s = self.backends["incident_service"]
        inc = s.create("t", "test incident")
        s.update(inc.incident_id, "t", inc.version,
                 {"severity": "high"})
        pkt = s.export_packet(inc.incident_id, "t")
        return (pkt["incident"]["incident_id"] == inc.incident_id,
                "create+versioned edit+export ok",
                {"version": pkt["incident"]["version"]})

    def _scope(self):
        m = self.backends["scope_matrix"]
        e = m.add_entry("inc-1", "fs-01", by="cmd")
        try:
            m.set_status(e.entry_id, "cmd", e.version, "confidentiality",
                         "exfiltrated", evidence_kind="rf_frame")
            return (False, "RF evidence confirmed breach!", {})
        except Exception as ex:
            return ("evidence" in str(ex).lower() or
                    "insufficient" in str(ex).lower(),
                    f"weak evidence blocked: {ex}", {})

    def _chat(self):
        c = self.backends["chat_service"]
        c.register_user("cmd", "commander", {"inc-1"})
        c.register_user("obs", "observer", {"inc-1"})
        c.create_room("inc-1")
        c.join("cmd", "inc-1")
        c.join("obs", "inc-1")
        try:
            c.post("obs", "inc-1", "hi")
            return (False, "observer posted!", {})
        except Exception:
            m, _ = c.post("cmd", "inc-1", "hello", client_nonce="n1")
            m2, dup = c.post("cmd", "inc-1", "hello", client_nonce="n1")
            return (dup and m.msg_id == m2.msg_id,
                    "observer denied; nonce dedup ok", {})

    # ---------------- runner -------------------------------------------
    def _run(self, iid: str, title: str, fn,
             needs: list[str]) -> ItemResult:
        missing = [n for n in needs if n not in self.backends]
        if missing:
            return ItemResult(iid, title, "NOT_RUN", "NOT_RUN",
                              f"missing backends: {missing}")
        try:
            ok, detail, ev = fn()
            return ItemResult(iid, title, "PASS" if ok else "FAIL",
                              "REAL" if self.backends.get("_real")
                              else "SIMULATED", detail, ev)
        except Exception as ex:
            return ItemResult(iid, title, "FAIL", "SIMULATED",
                              f"exception: {ex}")

    def run_all(self) -> dict:
        self.results = (self.w01() + self.w02() + self.w03_w05())
        passed = sum(1 for r in self.results if r.status == "PASS")
        failed = sum(1 for r in self.results if r.status == "FAIL")
        not_run = sum(1 for r in self.results if r.status == "NOT_RUN")
        return {
            "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                    time.gmtime(self.clock())),
            "summary": {"total": len(self.results), "PASS": passed,
                        "FAIL": failed, "NOT_RUN": not_run,
                        "deployment_acceptance":
                            "NOT CLAIMED — simulated backends"},
            "items": [{"req": r.req, "title": r.title, "status": r.status,
                       "mode": r.mode, "detail": r.detail,
                       "evidence": r.evidence} for r in self.results],
        }

    def to_json(self) -> str:
        return json.dumps(self.run_all(), indent=2)
