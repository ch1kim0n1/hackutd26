"""AppState — wires the existing in-memory services into one facade.

Dev-mode provisioning: demo users are seeded and machine-principal
tokens are issued directly into IdentityService.sessions (the same
mechanism login() uses for humans). No passwords, no external IdP.
"""
from __future__ import annotations

import os
import secrets
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .paths import ensure_service_paths  # noqa: F401  (sys.path first)

ensure_service_paths()

from containment_executor.service import ExecutorService  # noqa: E402
from containment_policy import ContainmentPolicy  # noqa: E402
from identity.models import PrincipalKind, Role  # noqa: E402
from identity.service import IdentityService  # noqa: E402
from incident_records.service import IncidentService  # noqa: E402
from investigator.agent import InvestigationAgent  # noqa: E402
from investigator.service_backends import ServiceBackends  # noqa: E402
from investigator.scripted import FakeResponse, ScriptedModel, tc  # noqa: E402
from investigator.tools import ToolContext, registry_from_backends  # noqa: E402
from nemotron_client.provider import ProviderInfo, build_chat_model  # noqa: E402
from response_audit.audit import AuditLog  # noqa: E402
from scope_matrix.service import ScopeMatrix  # noqa: E402

# Deterministic canned investigation: read observations + assets, then
# report. Used because no live Nemotron endpoint exists (Milestone 4).
_INVESTIGATION_SCRIPT = [
    FakeResponse(tool_calls=[
        tc("get_recent_observations", {"incident_id": "", "limit": 10}),
        tc("get_authorized_assets", {"zone_id": "rack-01"}),
        # Deterministic path requests physical verification on the surveyed
        # rack checkpoint. Scope-checked per incident — denied (recorded,
        # fail-soft) for incidents outside rack-01's waypoint registry.
        tc("request_rover_inspection",
           {"zone_id": "rack-01", "waypoint_id": "wp-rack-a"}),
    ]),
    FakeResponse(content=(
        "Assessment: observations are consistent with an unauthorized "
        "device in the monitored zone. Confidence is limited to metadata "
        "evidence; physical verification recommended. Unknowns: payload "
        "contents, dwell time, intent.")),
]

# Lab containment allowlist (docs/08): only these targets may ever be
# proposed for isolation/blocking/credential actions.
DEFAULT_TARGETS = {
    "lab-ap-01", "lab-switch-01", "lab-port-07",
    "lab-vlan-10", "device-lab-01",
}


def load_waypoint_registry() -> dict[str, set[str]]:
    """zone_id -> surveyed waypoint ids, from the rover route survey
    (robotics/rover/config/routes.json — the same whitelist the mission
    contract enforces). Empty registry fails closed: inspection requests
    are denied rather than dispatched to unsurveyed coordinates."""
    import json
    from .paths import REPO_ROOT
    path = Path(os.environ.get(
        "SENTINEL_ROVER_ROUTES",
        str(REPO_ROOT / "robotics" / "rover" / "config" / "routes.json")))
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    out: dict[str, set[str]] = {}
    for zone in data.get("zones", []):
        zid = zone.get("id")
        if not zid:
            continue
        out[zid] = {w.get("id") for w in zone.get("waypoints", [])
                    if w.get("id")}
    return out


@dataclass
class InvestigatorStack:
    """Selected ChatModel + non-secret provider description (issue #111).
    Live Nemotron when NEMOTRON_* env is configured; the deterministic
    scripted investigation otherwise — identical API behavior either way."""
    model: object
    provider: ProviderInfo


def _default_investigator_stack() -> InvestigatorStack:
    model, info = build_chat_model(
        fallback=ScriptedModel(list(_INVESTIGATION_SCRIPT)))
    return InvestigatorStack(model=model, provider=info)


@dataclass
class AppState:
    identity: IdentityService = field(default_factory=IdentityService)
    incidents: IncidentService = field(default_factory=IncidentService)
    scope_matrix: ScopeMatrix = field(default_factory=ScopeMatrix)
    policy: ContainmentPolicy = field(default_factory=lambda: ContainmentPolicy(
        allowed_targets=set(
            os.environ.get("SENTINEL_POLICY_TARGETS", "").split(",")
        ) - {""} or DEFAULT_TARGETS,
        fingerprint_secret=(
            os.environ.get("SENTINEL_POLICY_SECRET")
            or secrets.token_hex(32)  # ephemeral per boot; documented
        ).encode(),
    ))
    audit: AuditLog = field(default_factory=AuditLog)
    executor: ExecutorService = field(default_factory=ExecutorService)
    investigator_stack: InvestigatorStack = field(
        default_factory=_default_investigator_stack)
    investigation_runs: list[dict] = field(default_factory=list)
    # Live investigation backing stores (BlindSpot task): real persisted
    # observations, queued action requests, agent assessments/messages.
    observations: list[dict] = field(default_factory=list)
    mission_requests: list[dict] = field(default_factory=list)
    agent_assessments: list[dict] = field(default_factory=list)
    agent_messages: list[dict] = field(default_factory=list)
    # Integration wiring (BlindSpot E2E): surveyed waypoint registry for
    # tool scope checks, rover evidence artifact dir for inspection
    # report resolution, rover device id for mission requests.
    waypoints_by_zone: dict = field(
        default_factory=load_waypoint_registry)
    rover_evidence_dir: str = os.environ.get(
        "SENTINEL_ROVER_EVIDENCE_DIR", "")
    rover_device_id: str = os.environ.get(
        "SENTINEL_ROVER_DEVICE_ID", "rover-01")
    _agent_cache: dict = field(default_factory=dict)
    _orchestrator: object = field(default=None, repr=False)

    @property
    def investigator_model(self):
        """Backward-compatible alias for the selected ChatModel."""
        return self.investigator_stack.model

    def agent_model(self):
        """Model instance for one investigation run. Stateful scripted
        models fork so concurrent per-incident runs each get the full
        deterministic script; live/stateless models pass through."""
        model = self.investigator_stack.model
        return model.fork() if hasattr(model, "fork") else model

    @property
    def orchestrator(self):
        """Lazy event-driven orchestrator (#112)."""
        if self._orchestrator is None:
            from .orchestrator import Orchestrator
            self._orchestrator = Orchestrator(self)
        return self._orchestrator

    # ------------- seeding -------------
    def seed(self) -> dict[str, str]:
        """Create demo principals; return {username: user_id}.
        Machine principals get provisioned tokens (cannot human-login)."""
        # IdentityService bootstraps "admin-root" (username root-admin).
        bootstrap = "admin-root"
        cmd = self.identity.add_user(
            bootstrap, "commander", Role.COMMANDER, PrincipalKind.HUMAN)
        resp = self.identity.add_user(
            bootstrap, "responder", Role.RESPONDER, PrincipalKind.HUMAN)
        obs = self.identity.add_user(
            bootstrap, "observer", Role.OBSERVER, PrincipalKind.HUMAN)
        agent = self.identity.add_user(
            bootstrap, "agent-01", Role.AGENT, PrincipalKind.MACHINE)
        self.identity.add_user(
            bootstrap, "executor-01", Role.EXECUTOR,
            PrincipalKind.MACHINE)
        # provisioned machine tokens (documented dev mechanism).
        # SENTINEL_AGENT_TOKEN pins a stable token for service callers
        # (gateway observation forwarding, mission bridge) across restarts.
        tok_agent = os.environ.get("SENTINEL_AGENT_TOKEN") or \
            f"tok-{uuid.uuid4().hex[:16]}"
        self.identity.sessions[tok_agent] = agent.user_id
        return {
            "admin": bootstrap, "commander": cmd.user_id,
            "responder": resp.user_id, "observer": obs.user_id,
            "agent": agent.user_id, "agent_token": tok_agent,
        }

    # ------------- helpers -------------
    def actor(self, token: str) -> str | None:
        return self.identity.sessions.get(token)

    def role_of(self, actor_id: str) -> Role | None:
        u = self.identity.users.get(actor_id)
        return u.role if u else None

    def require_role(self, actor_id: str, *roles: Role) -> bool:
        return self.role_of(actor_id) in set(roles)

    def investigator_for(self, incident_id: str) -> InvestigationAgent:
        """One agent+registry per incident scope (cached).
        Operational path uses ServiceBackends — real stored observations,
        scope assets, evidence and policy proposals. FakeBackends remains
        for isolated tests only."""
        if incident_id not in self._agent_cache:
            try:
                inc = self.incidents.get(incident_id)
                zone_ids = {inc.zone_id} if inc.zone_id else set()
            except Exception:
                zone_ids = set()
            device_ids = {o.get("device_id") for o in self.observations
                          if o.get("device_id")}
            waypoint_ids = set()
            for z in zone_ids:
                waypoint_ids |= self.waypoints_by_zone.get(z, set())
            ctx = ToolContext(incident_id=incident_id,
                              allowed_zones=zone_ids,
                              allowed_devices=device_ids,
                              allowed_waypoints=waypoint_ids)
            backends = ServiceBackends(self, incident_id)
            registry = registry_from_backends(ctx, backends.as_backends())
            self._agent_cache[incident_id] = InvestigationAgent(
                self.agent_model(), registry)
        return self._agent_cache[incident_id]


def build_state(seed: bool = True) -> AppState:
    state = AppState()
    if seed:
        state.seed()
    return state
