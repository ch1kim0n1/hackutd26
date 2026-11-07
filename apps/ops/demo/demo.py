"""OPS-38: deterministic stage demo runner.

Emits a timed transcript of the 90-second full demo / 3-minute Winstead
demo as SCRIPTED steps — every step labeled SIMULATED until run against
the live stack. Never mislabels replay as live: `mode` is explicit.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DemoStep:
    t: float
    actor: str
    action: str
    expected: str
    mode: str = "SIMULATED"     # SIMULATED | LIVE — never ambiguous


# 90-second full demo script (docs/10)
FULL_DEMO_90S = [
    DemoStep(0, "operator", "open command center, login as commander",
             "dashboard loads, role shown", "SIMULATED"),
    DemoStep(10, "system", "rogue AP + cabinet-open correlate -> CORR01",
             "incident candidate appears w/ evidence links"),
    DemoStep(25, "nemotron", "investigation agent runs 3+ tools",
             "grounded report: findings+unknowns+alternates"),
    DemoStep(40, "commander", "approve containment proposal",
             "approval bound to action fingerprint"),
    DemoStep(55, "executor", "lab isolation applied + independently verified",
             "VERIFIED status, audit chain complete"),
    DemoStep(70, "team", "chat system post + scope matrix update",
             "responder sees live scope + chat"),
    DemoStep(85, "operator", "export incident packet",
             "JSON+MD packet w/ timeline+evidence"),
]

# 3-minute Winstead demo adds W01-W05 adversarial beats
WINSTEAD_3M = FULL_DEMO_90S + [
    DemoStep(95, "red-team", "lab-hostile principal attempts mgmt access",
             "denied at access matrix (W01a)"),
    DemoStep(110, "admin", "add responder, revoke observer mid-demo",
             "audited; revoked loses access instantly (W02a/d)"),
    DemoStep(130, "observer", "attempt cross-incident read + chat post",
             "denied (W02c/W05b)"),
    DemoStep(150, "attacker", "replay telemetry + forge signature",
             "dropped by relay (W01c)"),
]


def run_demo(steps: list[DemoStep], clock=time.time,
             speed: float = 0.0) -> dict:
    """'Run' the script — emits transcript. speed=0 -> instant (CI);
    speed>0 -> realtime pacing for stage."""
    transcript = []
    t0 = clock()
    for s in steps:
        if speed:
            target = t0 + s.t / speed
            while clock() < target:
                time.sleep(0.05)
        transcript.append({"t": s.t, "actor": s.actor,
                           "action": s.action, "expected": s.expected,
                           "mode": s.mode})
    return {"demo": "winstead" if len(steps) > 7 else "full",
            "steps": len(steps), "mode": steps[0].mode,
            "transcript": transcript,
            "disclaimer": "SIMULATED transcript — not live evidence" 
                          if steps[0].mode == "SIMULATED" else ""}


def write_transcript(rep: dict, path: str | Path) -> Path:
    p = Path(path)
    p.write_text(json.dumps(rep, indent=2))
    return p
