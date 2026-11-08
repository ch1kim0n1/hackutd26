"""Event-driven investigator orchestration (issue #112).

Backend observations and posture findings arrive as InvestigationEvents
(via POST /internal/events or an in-process source). Each unique
(event_id, incident_id) pair triggers exactly one investigation run —
no manual prompting. Runs go through the same hardened agent stack as
manual investigations: ToolGuard budgets/allowlist, ModelOutputGuard
citation + authority-claim validation, and per-incident agent caches.

Run records are appended to state.investigation_runs with explicit
provenance (event provenance + provider mode) so LIVE vs MOCK is never
ambiguous. No actuator calls: the agent may only use the existing
tool allowlist; containment stays proposal-only pending #113.
"""
from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Protocol

from investigator.agent import InvestigationAgent
from investigator.backends import FakeBackends
from investigator.tools import ToolContext, registry_from_backends

from agent_safety import HardenedAgent, ModelOutputGuard, ToolGuard

# Event kinds that warrant an automatic investigation. Observation kinds
# mirror spacetimedb/src/lib.ts; "posture_finding" covers Team B posture
# engine output (#126) once #102's scheduler lands.
TRIGGER_KINDS = {
    "wifi_ap_seen", "wifi_probe", "ble_beacon", "ble_beacon_seen",
    "contact_open", "cabinet_contact_open", "motion", "rf_frame_meta",
    "tag_seen", "device_offline", "posture_finding",
}

# Kinds that are noise for autonomous triggering (health heartbeats,
# routine mission progress, explicit close events).
IGNORED_KINDS = {
    "device_health", "contact_closed", "cabinet_contact_closed",
    "mission_status", "photo_captured", "door_state", "signal_strength",
    "temperature",
}

MAX_TOOL_CALLS_DEFAULT = int(os.environ.get("SENTINEL_ORCH_MAX_TOOL_CALLS", "8"))


@dataclass(frozen=True)
class InvestigationEvent:
    """One backend observation/finding normalized for orchestration."""
    event_id: str
    kind: str
    source: str = "observation"          # observation | finding | manual
    device_id: str = ""
    zone_id: str = ""
    incident_id: str | None = None
    summary: str = ""
    provenance: str = "LIVE"             # LIVE | MOCK | DEMO | REPLAY
    observed_at: str = ""
    data: dict = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict) -> "InvestigationEvent":
        return cls(
            event_id=str(payload.get("event_id") or payload.get("id") or ""),
            kind=str(payload.get("kind") or payload.get("type") or ""),
            source=str(payload.get("source") or "observation"),
            device_id=str(payload.get("device_id") or ""),
            zone_id=str(payload.get("zone_id") or ""),
            incident_id=(str(payload["incident_id"])
                         if payload.get("incident_id") else None),
            summary=str(payload.get("summary") or payload.get("data_json")
                        or payload.get("data") or "")[:2000],
            provenance=str(payload.get("provenance") or "LIVE"),
            observed_at=str(payload.get("observed_at") or ""),
            data=payload.get("data") if isinstance(payload.get("data"), dict) else {},
        )

    @property
    def dedupe_key(self) -> tuple[str, str]:
        return (self.event_id, self.incident_id or "")


class EventSource(Protocol):
    def poll(self) -> list[InvestigationEvent]: ...


class MemoryEventSource:
    """In-process queue — tests, embedded use, and the HTTP ingest path
    all share this through Orchestrator.enqueue()."""

    def __init__(self) -> None:
        self._queue: Deque[InvestigationEvent] = deque()

    def push(self, event: InvestigationEvent) -> None:
        self._queue.append(event)

    def poll(self) -> list[InvestigationEvent]:
        out = list(self._queue)
        self._queue.clear()
        return out


class Orchestrator:
    """Drains backend events into deduplicated, hardened investigations."""

    def __init__(self, state, *, max_tool_calls: int = MAX_TOOL_CALLS_DEFAULT,
                 source: EventSource | None = None):
        self.state = state
        self.max_tool_calls = max_tool_calls
        self.source = source or MemoryEventSource()
        self._pending: Deque[InvestigationEvent] = deque()
        self._seen: set[tuple[str, str]] = set()
        self._agents: dict[str, HardenedAgent] = {}
        self.processed: dict[tuple[str, str], str] = {}
        self.stats = {"received": 0, "triggered": 0, "duplicates": 0,
                      "ignored": 0, "failed": 0}

    # ---------------- intake ----------------
    def enqueue(self, event: InvestigationEvent) -> str:
        """Returns 'accepted' | 'duplicate' | 'ignored'."""
        self.stats["received"] += 1
        if not event.event_id:
            self.stats["failed"] += 1
            return "invalid"
        if event.kind in IGNORED_KINDS:
            self.stats["ignored"] += 1
            return "ignored"
        if event.kind not in TRIGGER_KINDS:
            # Unknown kinds are accepted — new observation kinds should
            # not silently drop investigations; the kind is recorded.
            pass
        key = self._resolve_key(event)
        if key in self._seen:
            self.stats["duplicates"] += 1
            return "duplicate"
        self._seen.add(key)
        self._pending.append(event)
        self.stats["triggered"] += 1
        return "accepted"

    @staticmethod
    def _resolve_key(event: InvestigationEvent) -> tuple[str, str]:
        # Unlinked events dedupe on (event_id, "") permanently — the
        # auto-created incident is resolved at run time and must not
        # change the idempotency key on redelivery.
        return event.dedupe_key

    def poll_source(self) -> int:
        """Pull new events from the configured source into the queue."""
        n = 0
        for ev in self.source.poll():
            self.enqueue(ev)
            n += 1
        return n

    # ---------------- execution ----------------
    def pump(self) -> list[dict]:
        """Run pending investigations; returns new run records."""
        runs = []
        while self._pending:
            event = self._pending.popleft()
            try:
                runs.append(self._run(event))
            except Exception as exc:  # one bad event must not stall queue
                self.stats["failed"] += 1
                runs.append({
                    "event_id": event.event_id, "kind": event.kind,
                    "incident_id": event.incident_id, "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "provenance": event.provenance,
                })
        return runs

    def _agent_for(self, incident_id: str) -> HardenedAgent:
        if incident_id not in self._agents:
            backends = FakeBackends()
            ctx = ToolContext(
                incident_id=incident_id,
                allowed_zones={"rack-01", "lab-b", "lobby"},
                allowed_devices={"device-lab-01", "lab-ap-01"})
            registry = registry_from_backends(ctx, backends.as_backends())
            inner = InvestigationAgent(self.state.investigator_model, registry,
                                       max_tool_calls=self.max_tool_calls)
            allowed = {s["name"] for s in registry.specs()}
            self._agents[incident_id] = HardenedAgent(
                inner,
                ToolGuard(allowed, max_calls=self.max_tool_calls),
                ModelOutputGuard(known_evidence_ids=set(backends.evidence)))
        return self._agents[incident_id]

    def _run(self, event: InvestigationEvent) -> dict:
        incident_id = event.incident_id or self._ensure_incident(event)
        agent = self._agent_for(incident_id)
        brief = self._brief(event)
        result = agent.investigate(brief)
        a = result.inner_result
        budget_hit = (a.tool_calls_made >= self.max_tool_calls
                      or a.degraded)
        run = {
            "event_id": event.event_id,
            "incident_id": incident_id,
            "kind": event.kind,
            "source": event.source,
            "by": "orchestrator",
            "brief": brief,
            "provenance": event.provenance,
            "provider_mode": self.state.investigator_stack.provider.mode,
            "status": ("completed" if result.assessment_accepted
                       else "rejected" if result.assessment_violations
                       else "degraded"),
            "budget_exhausted": budget_hit,
            "assessment": _assessment_dict(a),
            "trace": list(getattr(a, "trace", []) or []),
            "tool_calls_made": a.tool_calls_made,
            "citations": list(a.evidence_ids),
            "assessment_accepted": result.assessment_accepted,
            "assessment_violations": result.assessment_violations,
            "denied_tool_calls": result.denied_tool_calls,
            "guard_trace": result.guard_trace,
            "dedupe_key": list(event.dedupe_key),
        }
        self.state.investigation_runs.append(run)
        self.processed[(event.event_id, incident_id)] = run["status"]
        return run

    def _ensure_incident(self, event: InvestigationEvent) -> str:
        """Auto-create an incident for unlinked observations so the run
        has an auditable scope. Deterministic per event_id."""
        from incident_records.models import Severity
        inc = self.state.incidents.create(
            "orchestrator",
            title=f"Auto-investigation: {event.kind} {event.device_id}".strip(),
            summary=event.summary or f"{event.kind} observed on "
                                     f"{event.device_id or 'unknown device'}",
            severity=Severity.MEDIUM,
            zone_id=event.zone_id or "",
            provenance={"source": "orchestrator", "event_id": event.event_id,
                        "event_provenance": event.provenance,
                        "event_kind": event.kind})
        return inc.incident_id

    @staticmethod
    def _brief(event: InvestigationEvent) -> str:
        parts = [f"Autonomous investigation trigger: {event.kind}"]
        if event.device_id:
            parts.append(f"device={event.device_id}")
        if event.zone_id:
            parts.append(f"zone={event.zone_id}")
        if event.summary:
            parts.append(f"summary={event.summary}")
        if event.data:
            parts.append(f"data={event.data}")
        return "; ".join(parts)

    def status(self) -> dict:
        return {
            "stats": dict(self.stats),
            "pending": len(getattr(self.source, "_queue", ())),
            "processed": len(self.processed),
            "max_tool_calls": self.max_tool_calls,
            "provider_mode": self.state.investigator_stack.provider.mode,
        }


def _assessment_dict(a) -> dict:
    from dataclasses import asdict
    d = asdict(a)
    d.pop("trace", None)  # trace is stored at run top level
    return d
