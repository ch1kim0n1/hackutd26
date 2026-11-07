"""Network segmentation + service access matrix (docs/06 R01).

The lab network is hostile: EVERY path is denied unless explicitly
allowlisted. The control plane lives on the management segment; the
only permitted lab interaction is the outbound-only collector relay.
This module is the policy source of truth — services consult it, they
do not embed their own rules."""
from __future__ import annotations

from enum import Enum


class Segment(str, Enum):
    MANAGEMENT = "management"   # control plane host/network
    LAB = "lab"                 # hostile office/test network
    BRIDGE = "bridge"           # constrained gateway (data-only)


class Principal(str, Enum):
    OPERATOR = "operator"       # authenticated human on management net
    DEVICE = "device"           # sensor/rover service identity
    AGENT = "agent"             # Nemotron worker
    EXECUTOR = "executor"       # lab action executor
    LAB_HOSTILE = "lab_hostile" # anything on the lab segment
    ANONYMOUS = "anonymous"


class Service(str, Enum):
    DASHBOARD_API = "dashboard_api"
    CHAT = "chat"
    SPACETIMEDB = "spacetimedb"
    EVIDENCE = "evidence"
    RELAY = "relay"             # lab->mgmt observation channel
    CONTAINMENT = "containment" # approval-gated action API
    ADMIN = "admin"


# Default-deny matrix: (segment, principal, service) -> allowed?
# Anything not listed is DENIED.
ALLOW: set[tuple[Segment, Principal, Service]] = {
    # operators on management net reach everything except nothing special
    (Segment.MANAGEMENT, Principal.OPERATOR, Service.DASHBOARD_API),
    (Segment.MANAGEMENT, Principal.OPERATOR, Service.CHAT),
    (Segment.MANAGEMENT, Principal.OPERATOR, Service.SPACETIMEDB),
    (Segment.MANAGEMENT, Principal.OPERATOR, Service.EVIDENCE),
    (Segment.MANAGEMENT, Principal.OPERATOR, Service.ADMIN),
    # devices only push observations through the relay — nothing else
    (Segment.BRIDGE, Principal.DEVICE, Service.RELAY),
    # agent worker: reads via API, proposes via containment API (proposal only)
    (Segment.MANAGEMENT, Principal.AGENT, Service.DASHBOARD_API),
    (Segment.MANAGEMENT, Principal.AGENT, Service.CONTAINMENT),
    # operators may reach the containment API but still need a
    # server-side approval token — reachability != authorization
    (Segment.MANAGEMENT, Principal.OPERATOR, Service.CONTAINMENT),
    # executor: reaches containment service for approved actions only
    (Segment.MANAGEMENT, Principal.EXECUTOR, Service.CONTAINMENT),
    # lab segment: NOTHING reaches management services — not even relay
    # inbound; the relay is outbound-initiated from bridge side.
}

# Services that additionally require a valid session/approval token —
# segment+principal allow is necessary but NOT sufficient.
TOKEN_GATED = {Service.CONTAINMENT, Service.ADMIN, Service.EVIDENCE,
               Service.SPACETIMEDB, Service.CHAT, Service.DASHBOARD_API}


def authorize(segment: Segment, principal: Principal,
              service: Service) -> tuple[bool, str]:
    """Default-deny check. Returns (allowed, reason)."""
    if (segment, principal, service) in ALLOW:
        return True, "allowlisted"
    return False, (f"denied: {principal.value}@{segment.value} -> "
                   f"{service.value} not in access matrix")


def requires_token(service: Service) -> bool:
    return service in TOKEN_GATED
