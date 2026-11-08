#!/usr/bin/env python3
"""Generate examples/sample-decision-log.jsonl — issue #105 evidence.

Builds a small demo policy (allow authorized lab http, block a listed
hostile source, redirect ssh probes to the rover decoy, default-deny
unmatched), evaluates a handful of SIMULATED flows and writes the
hash-chained decision log. All flows are DEMO provenance — nothing
here is LIVE traffic and nothing is really enforced.

Run from apps/defense/gateway:
    PYTHONPATH=src python3 examples/make_sample_log.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from defense_gateway import (  # noqa: E402
    DecisionEngine,
    DecisionLog,
    DefaultAction,
    FlowDecisionKind,
    FlowEndpoint,
    FlowMatch,
    FlowPolicy,
    FlowRule,
    FlowTuple,
    Provenance,
    SimulatedEnforcementPoint,
)

OUT = Path(__file__).resolve().parent / "sample-decision-log.jsonl"

DECOY = FlowEndpoint("rover-decoy-01", "http")

POLICY = FlowPolicy(
    policy_id="pol-edge-demo",
    version=1,
    default_action=DefaultAction.DENY,
    default_ttl_s=60.0,
    rules=[
        FlowRule("allow-lab-http", FlowMatch(src_node="lab-client-01",
                                             dst_service="http"),
                 FlowDecisionKind.ALLOW,
                 reason="authorized lab client to protected http"),
        FlowRule("block-known-bad", FlowMatch(src_node="bad-actor-01"),
                 FlowDecisionKind.BLOCK,
                 reason="deny listed hostile lab source", ttl_s=30.0),
        FlowRule("redirect-ssh-to-decoy", FlowMatch(dst_service="ssh"),
                 FlowDecisionKind.REDIRECT, redirect_to=DECOY,
                 reason="route ssh probes to rover decoy"),
    ],
)

FLOWS = [
    # (flow_id, src node/service, dst node/service, provenance)
    ("flow-demo-001", "lab-client-01", "https", "dc-pi-02", "http", Provenance.DEMO),
    ("flow-demo-002", "bad-actor-01", "https", "dc-pi-02", "http", Provenance.DEMO),
    ("flow-demo-003", "lab-client-01", "https", "dc-pi-02", "ssh", Provenance.DEMO),
    ("flow-demo-004", "guest-laptop", "https", "dc-pi-02", "ssh", Provenance.DEMO),
    ("flow-demo-005", "unknown-scanner", "http", "dc-pi-09", "https", Provenance.REPLAY),
]


def main() -> None:
    engine = DecisionEngine(POLICY)
    enforcer = SimulatedEnforcementPoint()
    log = DecisionLog(OUT)
    if OUT.exists():
        OUT.unlink()
        log = DecisionLog(OUT)

    receipts = []
    for fid, sn, ss, dn, ds, prov in FLOWS:
        f = FlowTuple(flow_id=fid,
                      src=FlowEndpoint(sn, ss), dst=FlowEndpoint(dn, ds),
                      provenance=prov)
        d = engine.evaluate(f, trace_id=f"demo-{fid}")
        log.append(d)
        receipts.append(enforcer.apply(d).as_record())

    ok, msg = log.verify()
    print(f"wrote {len(log.records_list)} decision records -> {OUT}")
    print(f"chain verify: {ok} ({msg})")
    print("enforcement receipts (all simulated):")
    for r in receipts:
        print(f"  {r['flow_id']}: {r['result']}"
              + (f" -> {r['redirect_target']}" if r["redirect_target"] else ""))


if __name__ == "__main__":
    main()
