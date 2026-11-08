"""FastAPI facade over the existing SENTINEL HIVE Python services.

Every request is authenticated by bearer token (IdentityService
sessions) and authorized per-request via IdentityService.authorize —
role capability + incident scope + audit on every check. State is
in-memory: restart loses everything (documented, per issue #96).
"""
from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .state import AppState, build_state

PROVENANCE = "LIVE"          # service-derived data, not a fixture
BACKEND = "in-memory"        # ephemeral; no persistence in this facade


def _env(payload: Any) -> dict:
    """Attach provenance/backend labels to every response object."""
    if isinstance(payload, dict):
        return {**payload, "provenance": PROVENANCE,
                "state_backend": BACKEND}
    return {"data": payload, "provenance": PROVENANCE,
            "state_backend": BACKEND}


def _asdict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, (list, tuple)):
        return [_asdict(x) for x in obj]
    return obj


# ---------------------------------------------------------------- models
class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)


class IncidentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=4000)
    severity: str = "medium"
    zone_id: str = Field(default="", max_length=64)
    provenance: dict = Field(default_factory=dict)


class IncidentPatch(BaseModel):
    expected_version: int = Field(ge=1)
    fields: dict[str, Any] = Field(default_factory=dict)


class TransitionIn(BaseModel):
    to_state: str = Field(min_length=1, max_length=32)
    expected_version: int = Field(ge=1)
    reason: str = Field(default="", max_length=500)


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class EvidenceIn(BaseModel):
    evidence_id: str = Field(min_length=1, max_length=128)
    kind: str = Field(min_length=1, max_length=32)
    note: str = Field(default="", max_length=500)


class ScopeEntryIn(BaseModel):
    incident_id: str = Field(min_length=1, max_length=64)
    asset_id: str = Field(min_length=1, max_length=64)
    dataset: str = Field(default="", max_length=128)


class InvestigationIn(BaseModel):
    incident_id: str = Field(min_length=1, max_length=64)
    brief: str = Field(default="", max_length=4000)


class ProposalIn(BaseModel):
    incident_id: str = Field(min_length=1, max_length=64)
    action_type: str = Field(min_length=1, max_length=64)
    target_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=8, max_length=500)
    ttl_s: float = Field(default=300.0, gt=0, le=3600)
    scope: dict = Field(default_factory=dict)


class ApprovalIn(BaseModel):
    proposal_id: str = Field(min_length=1, max_length=64)
    decision: str = Field(min_length=1, max_length=16)
    fingerprint: str = Field(min_length=1, max_length=128)
    reason: str = Field(default="", max_length=500)


class UserIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    role: str = Field(min_length=1, max_length=32)


class RoleIn(BaseModel):
    role: str = Field(min_length=1, max_length=32)


class ScopeIn(BaseModel):
    incident_ids: list[str] = Field(default_factory=list)


class ExecuteIn(BaseModel):
    doc: dict[str, Any]


# ------------------------------------------------------------------ app
def create_app(seed: bool = True) -> FastAPI:
    state = build_state(seed=seed)
    app = FastAPI(title="SENTINEL HIVE API", version="0.1.0")
    app.state.svc = state

    # ---------------- auth ----------------
    def actor(authorization: str | None = Header(default=None)) -> str:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "bearer token required")
        uid = state.actor(authorization[7:].strip())
        if uid is None:
            raise HTTPException(401, "unknown or expired token")
        return uid

    def gate(uid: str, access, incident_id: str | None = None) -> None:
        from identity.models import Access as _A  # local: path bootstrap
        dec = state.identity.authorize(uid, _A(access), incident_id)
        if not dec.allowed:
            raise HTTPException(403, f"denied: {dec.reason}")

    def get_incident_or_404(iid: str):
        try:
            return state.incidents.get(iid)
        except KeyError:
            raise HTTPException(404, f"unknown incident {iid}")

    # ---------------- health ----------------
    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "service": "sentinel-api",
                "state_backend": BACKEND,
                # non-secret provider mode (issue #111): live|fake + reason
                "agent_provider": _asdict(
                    state.investigator_stack.provider)}

    @app.get("/readyz")
    def readyz():
        ready = all([
            state.identity is not None, state.incidents is not None,
            state.scope_matrix is not None, state.policy is not None,
            state.audit is not None, state.executor is not None,
        ])
        return {"ready": ready, "state_backend": BACKEND,
                "services": ["identity", "incidents", "scope_matrix",
                             "policy", "audit", "executor", "investigator"]}

    # ---------------- auth ----------------
    @app.post("/auth/login")
    def login(body: LoginIn):
        tok = state.identity.login(body.username, password_ok=True)
        if tok is None:
            raise HTTPException(401, "login denied (unknown, machine, "
                                     "suspended or revoked principal)")
        uid = state.actor(tok)
        return _env({"token": tok, "user_id": uid,
                     "role": state.role_of(uid).value})

    @app.post("/auth/logout")
    def logout(authorization: str | None = Header(default=None)):
        if authorization and authorization.startswith("Bearer "):
            state.identity.logout(authorization[7:].strip())
        return {"logged_out": True}

    # ---------------- users / RBAC admin ----------------
    @app.get("/users")
    def list_users(uid: str = Depends(actor)):
        gate(uid, "manage_users")
        return _env({"users": [_asdict(u) for u in
                               state.identity.users.values()]})

    @app.post("/users")
    def add_user(body: UserIn, uid: str = Depends(actor)):
        gate(uid, "manage_users")
        from identity.models import PrincipalKind, Role as _R
        machine = body.role in {"agent", "device", "executor"}
        try:
            u = state.identity.add_user(
                uid, body.username, _R(body.role),
                PrincipalKind.MACHINE if machine
                else PrincipalKind.HUMAN)
        except (ValueError, KeyError) as e:
            raise HTTPException(400, str(e))
        return _env(_asdict(u))

    @app.post("/users/{target}/revoke")
    def revoke_user(target: str, uid: str = Depends(actor)):
        gate(uid, "manage_users")
        try:
            state.identity.revoke_user(uid, target)
        except KeyError:
            raise HTTPException(404, "unknown user")
        return {"revoked": target}

    @app.post("/users/{target}/role")
    def change_role(target: str, body: RoleIn, uid: str = Depends(actor)):
        gate(uid, "manage_roles")
        from identity.models import Role as _R
        try:
            state.identity.change_role(uid, target, _R(body.role))
        except (KeyError, ValueError) as e:
            raise HTTPException(400, str(e))
        return {"user_id": target, "role": body.role}

    @app.post("/users/{target}/scope")
    def set_scope(target: str, body: ScopeIn, uid: str = Depends(actor)):
        gate(uid, "manage_users")
        try:
            state.identity.set_incident_scope(uid, target,
                                              set(body.incident_ids))
        except KeyError:
            raise HTTPException(404, "unknown user")
        return {"user_id": target, "incident_scope": body.incident_ids}

    # ---------------- incidents ----------------
    @app.get("/incidents")
    def list_incidents(uid: str = Depends(actor)):
        from identity.models import Access as _A
        out = []
        for inc in state.incidents.incidents.values():
            if state.identity.authorize(uid, _A.READ_INCIDENT,
                                        inc.incident_id).allowed:
                out.append(_asdict(inc))
        return _env({"items": out, "count": len(out)})

    @app.post("/incidents", status_code=201)
    def create_incident(body: IncidentCreate, uid: str = Depends(actor)):
        gate(uid, "write_incident")
        from incident_records.models import Severity
        try:
            inc = state.incidents.create(
                uid, body.title, body.summary,
                severity=Severity(body.severity), zone_id=body.zone_id,
                provenance=body.provenance)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return _env(_asdict(inc))

    @app.get("/incidents/{iid}")
    def get_incident(iid: str, uid: str = Depends(actor)):
        gate(uid, "read_incident", iid)
        return _env(_asdict(get_incident_or_404(iid)))

    @app.patch("/incidents/{iid}")
    def patch_incident(iid: str, body: IncidentPatch,
                       uid: str = Depends(actor)):
        gate(uid, "write_incident", iid)
        get_incident_or_404(iid)
        from incident_records.models import VersionConflict
        try:
            inc = state.incidents.update(iid, uid, body.expected_version,
                                         body.fields)
        except VersionConflict as e:
            raise HTTPException(409, str(e))
        except (ValueError, KeyError) as e:
            raise HTTPException(400, str(e))
        return _env(_asdict(inc))

    @app.post("/incidents/{iid}/transition")
    def transition(iid: str, body: TransitionIn,
                   uid: str = Depends(actor)):
        gate(uid, "write_incident", iid)
        get_incident_or_404(iid)
        from incident_records.models import (IncidentState,
                                             InvalidTransition,
                                             VersionConflict)
        try:
            inc = state.incidents.transition(
                iid, uid, IncidentState(body.to_state),
                body.expected_version, body.reason)
        except VersionConflict as e:
            raise HTTPException(409, str(e))
        except (InvalidTransition, ValueError) as e:
            raise HTTPException(409, str(e))
        return _env(_asdict(inc))

    @app.post("/incidents/{iid}/notes")
    def add_note(iid: str, body: NoteIn, uid: str = Depends(actor)):
        gate(uid, "write_incident", iid)
        get_incident_or_404(iid)
        inc = state.incidents.add_note(iid, uid, body.text)
        return _env({"incident_id": iid, "notes": inc.notes})

    @app.post("/incidents/{iid}/evidence", status_code=201)
    def link_evidence(iid: str, body: EvidenceIn,
                      uid: str = Depends(actor)):
        gate(uid, "upload_evidence", iid)
        get_incident_or_404(iid)
        inc = state.incidents.link_evidence(iid, uid, body.evidence_id,
                                            body.kind, body.note)
        return _env(_asdict(inc))

    @app.get("/incidents/{iid}/packet")
    def export_packet(iid: str, uid: str = Depends(actor)):
        gate(uid, "read_evidence", iid)
        get_incident_or_404(iid)
        return _env(state.incidents.export_packet(iid, uid))

    # ---------------- scope matrix (findings) ----------------
    @app.get("/incidents/{iid}/scope")
    def scope_entries(iid: str, uid: str = Depends(actor)):
        gate(uid, "read_incident", iid)
        get_incident_or_404(iid)
        return _env({"items": [_asdict(e) for e in
                               state.scope_matrix.entries_for_incident(iid)]})

    @app.post("/scope/entries", status_code=201)
    def add_scope_entry(body: ScopeEntryIn, uid: str = Depends(actor)):
        gate(uid, "write_incident", body.incident_id)
        get_incident_or_404(body.incident_id)
        e = state.scope_matrix.add_entry(body.incident_id, body.asset_id,
                                         dataset=body.dataset, by=uid)
        return _env(_asdict(e))

    # ---------------- investigations ----------------
    @app.post("/investigations", status_code=201)
    def run_investigation(body: InvestigationIn,
                          uid: str = Depends(actor)):
        gate(uid, "read_incident", body.incident_id)
        inc = get_incident_or_404(body.incident_id)
        brief = body.brief or inc.summary or inc.title
        agent = state.investigator_for(body.incident_id)
        assessment = agent.investigate(brief)
        run = {"incident_id": body.incident_id, "by": uid,
               "brief": brief, "assessment": _asdict(assessment)}
        state.investigation_runs.append(run)
        return _env(run["assessment"] | {"incident_id": body.incident_id,
                                         "run_index":
                                             len(state.investigation_runs)})

    @app.get("/investigations")
    def list_investigations(uid: str = Depends(actor)):
        from identity.models import Access as _A
        return _env({"items": [r for r in state.investigation_runs
                               if state.identity.authorize(
                                   uid, _A.READ_INCIDENT,
                                   r["incident_id"]).allowed]})

    # ---------------- containment proposals / approvals ----------------
    @app.post("/proposals", status_code=201)
    def propose(body: ProposalIn, uid: str = Depends(actor)):
        gate(uid, "propose_action", body.incident_id)
        get_incident_or_404(body.incident_id)
        role = state.role_of(uid)
        res = state.policy.propose(
            incident_id=body.incident_id, action_type=body.action_type,
            target_id=body.target_id, reason=body.reason,
            proposer_id=uid, proposer_role=role.value,
            ttl_s=body.ttl_s, scope=body.scope)
        if not res.ok:
            raise HTTPException(403, f"proposal denied: {res.reason}")
        return _env(_asdict(res.proposal))

    def _visible_proposals(uid: str):
        from identity.models import Access as _A
        return [p for p in state.policy.proposals.values()
                if state.identity.authorize(
                    uid, _A.READ_INCIDENT, p.incident_id).allowed]

    @app.get("/proposals")
    def list_proposals(uid: str = Depends(actor)):
        return _env({"items": [_asdict(p) for p in
                               _visible_proposals(uid)]})

    @app.get("/proposals/{pid}")
    def get_proposal(pid: str, uid: str = Depends(actor)):
        p = state.policy.proposals.get(pid)
        if p is None:
            raise HTTPException(404, "unknown proposal")
        gate(uid, "read_incident", p.incident_id)
        return _env(_asdict(p))

    @app.post("/approvals")
    def decide(body: ApprovalIn, uid: str = Depends(actor)):
        p = state.policy.proposals.get(body.proposal_id)
        if p is None:
            raise HTTPException(404, "unknown proposal")
        gate(uid, "approve_action", p.incident_id)
        role = state.role_of(uid)
        res = state.policy.decide(
            proposal_id=body.proposal_id, approver_id=uid,
            approver_role=role.value, decision=body.decision,
            fingerprint=body.fingerprint, reason=body.reason)
        status = 200 if res.ok else 403
        payload = {"ok": res.ok, "reason": res.reason,
                   "proposal": _asdict(res.proposal),
                   "approval": _asdict(res.approval) if res.approval
                   else None}
        if not res.ok:
            raise HTTPException(status, payload)
        return _env(payload)

    # ---------------- executor pickup ----------------
    def _role_value(uid: str) -> str:
        role = state.role_of(uid)
        return getattr(role, "value", role) or ""

    @app.get("/actions/approved")
    def approved_actions(uid: str = Depends(actor)):
        if _role_value(uid) not in {"admin", "commander", "executor"}:
            raise HTTPException(403, "approved-action feed restricted to "
                                     "admin/commander/executor")
        return _env({"items": [_asdict(p) for p in
                               state.policy.approved_actions()]})

    @app.post("/executor/execute")
    def executor_execute(body: ExecuteIn, uid: str = Depends(actor)):
        if _role_value(uid) not in {"admin", "executor"}:
            raise HTTPException(403, "executor endpoint restricted to "
                                     "admin/executor")
        try:
            code, record = state.executor.execute(body.doc)
        except (ValueError, KeyError) as e:
            raise HTTPException(400, str(e))
        return _env({"http_status": code, "record": record})

    # ---------------- audit ----------------
    @app.get("/audit")
    def audit_trail(incident_id: str | None = None,
                    uid: str = Depends(actor)):
        role = getattr(state.role_of(uid), "value", None)
        if role not in {"admin", "commander"}:
            raise HTTPException(403, "audit trail restricted to "
                                     "admin/commander")
        # identity.audit_trail holds every authorize/access_check record;
        # response_audit holds hash-chained containment events.
        id_audit = state.identity.audit_trail()
        resp_audit = state.audit.timeline(incident_id)
        return _env({
            "identity_audit": [_asdict(e) for e in id_audit],
            "response_audit": [_asdict(e) for e in resp_audit],
            "chain_valid": state.audit.verify()[0]})

    return app


app = create_app(seed=os.environ.get("SENTINEL_API_SEED", "1") == "1")
