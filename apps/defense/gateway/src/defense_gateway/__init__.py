"""defense_gateway — virtual defense gateway flow-decision contract.

Issue #105 (M3.1). Simulated allow/block/redirect decisions for
authorized lab traffic only. See README.md and docs/04 for the
contract; nothing in this package claims real network enforcement.
"""
from .enforcement import EnforcementOutcome, SimulatedEnforcementPoint
from .engine import DecisionEngine
from .log import DecisionLog, DecisionRecord
from .models import (
    ENGINE_VERSION,
    SCHEMA_VERSION,
    DefaultAction,
    EnforcementStatus,
    FlowDecision,
    FlowDecisionKind,
    FlowEndpoint,
    FlowMatch,
    FlowPolicy,
    FlowRule,
    FlowTuple,
    FlowValidationError,
    Provenance,
)

__all__ = [
    "DecisionEngine",
    "DecisionLog",
    "DecisionRecord",
    "DefaultAction",
    "ENGINE_VERSION",
    "EnforcementOutcome",
    "EnforcementStatus",
    "FlowDecision",
    "FlowDecisionKind",
    "FlowEndpoint",
    "FlowMatch",
    "FlowPolicy",
    "FlowRule",
    "FlowTuple",
    "FlowValidationError",
    "Provenance",
    "SCHEMA_VERSION",
    "SimulatedEnforcementPoint",
]
