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

from .paths import ensure_service_paths  # noqa: F401  (sys.path first)

ensure_service_paths()

from containment_executor.service import ExecutorService  # noqa: E402
from containment_policy import ContainmentPolicy  # noqa: E402
from identity.models import PrincipalKind, Role  # noqa: E402
from identity.service import IdentityService  # noqa: E402
from incident_records.service import IncidentService  # noqa: E402
from investigator.agent import InvestigationAgent  # noqa: E402
from investigator.backends import FakeBackends  # noqa: E402
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
    _agent_cache: dict = field(default_factory=dict)
    _orchestrator: object = field(default=None, repr=False)

    @property
    def investigator_model(self):
        """Backward-compatible alias for the selected ChatModel."""
        return self.investigator_stack.model

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
        # provisioned machine tokens (documented dev mechanism)
        tok_agent = f"tok-{uuid.uuid4().hex[:16]}"
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
        """One agent+registry per incident scope (cached)."""
        if incident_id not in self._agent_cache:
            backends = FakeBackends()
            ctx = ToolContext(incident_id=incident_id,
                              allowed_zones={"rack-01", "lab-b", "lobby"},
                              allowed_devices={"device-lab-01", "lab-ap-01"})
            registry = registry_from_backends(ctx, backends.as_backends())
            self._agent_cache[incident_id] = InvestigationAgent(
                self.investigator_stack.model, registry)
        return self._agent_cache[incident_id]


def build_state(seed: bool = True) -> AppState:
    state = AppState()
    if seed:
        state.seed()
    return state
