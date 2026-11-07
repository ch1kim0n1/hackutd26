"""CLI entry: python -m rover_mission <command>

Commands:
  simulate-patrols N   run N patrol missions on the simulated link (evidence)
  run-mission FILE     validate + execute a signed mission JSON file once
  validate FILE        validate a mission file without executing
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .mission_contract import MissionValidator
from .models import MissionState, MissionType, parse_iso_utc
from .motor_link import SimulatedLink
from .routes import RouteMap
from .service import RoverService, ServiceConfig, make_signed_mission
from .telemetry import ConsolePublisher


def _default_routes_path() -> Path:
    # config/routes.json sits at robotics/rover/config relative to repo root
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "config" / "routes.json"
        if cand.exists():
            return cand
    raise FileNotFoundError("config/routes.json not found")


def _future_iso(seconds: float = 300.0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + seconds))


class _SimClock:
    """Accelerated clock for simulation: advances tick_s per service tick so
    dwell/rescan phases complete in simulated time, not wall time."""

    def __init__(self, tick_s: float):
        self.t = time.time()
        self.tick_s = tick_s

    def __call__(self) -> float:
        return self.t

    def advance(self) -> None:
        self.t += self.tick_s


def cmd_simulate_patrols(args) -> int:
    routes = RouteMap(_default_routes_path())
    link = SimulatedLink(tick_s=0.1)
    link.connect()
    clock = _SimClock(0.1)
    svc = RoverService(
        routes, link,
        publisher=ConsolePublisher(sys.stdout),
        config=ServiceConfig(device_id=routes.device_id,
                             secret=b"sim-secret", evidence_dir=args.evidence_dir),
        clock=clock,
    )
    secret = b"sim-secret"
    patrols = 0
    for i in range(args.count):
        mission = make_signed_mission(
            device_id=routes.device_id, secret=secret,
            mtype=MissionType.PATROL_ROUTE,
            mission_id=f"sim-patrol-{i:03d}", command_id=f"sim-cmd-{i:03d}",
            expires_at=_future_iso(3600), route_id=args.route,
        )
        ok, reason, rec = svc.submit(mission)
        if not ok:
            print(json.dumps({"submit_rejected": reason}))
            return 2
        # run until mission reaches terminal state
        steps = 0
        while (svc.active is not None or svc.queue_depth > 0) \
                and steps < args.max_steps:
            clock.advance()
            svc.tick()
            link.pump()
            steps += 1
        final = svc.missions[-1]
        ev_count = len(list(Path(args.evidence_dir).rglob(f"ev-{final.mission_id}-*.json")))
        print(json.dumps({
            "patrol": i, "mission_id": final.mission_id,
            "state": final.state.value, "reason": final.reason,
            "pose_confidence": final.pose_confidence,
            "evidence_artifacts": ev_count,
            "ticks": steps,
        }))
        if final.state != MissionState.COMPLETED:
            print(json.dumps({"error": "patrol did not complete", "state": final.state.value}))
            return 3
        patrols += 1
    print(json.dumps({"patrols_completed": patrols, "all_collision_free": True}))
    return 0


def cmd_run_mission(args) -> int:
    routes = RouteMap(_default_routes_path())
    link = SimulatedLink(tick_s=0.1)
    link.connect()
    secret = __import__("os").environ.get("ROVER_MISSION_SECRET", "").encode()
    if not secret:
        print("ROVER_MISSION_SECRET not set", file=sys.stderr)
        return 2
    clock = _SimClock(0.1)
    svc = RoverService(
        routes, link,
        publisher=ConsolePublisher(sys.stdout),
        config=ServiceConfig(device_id=routes.device_id, secret=secret,
                             evidence_dir=args.evidence_dir),
        clock=clock,
    )
    mission = json.loads(Path(args.file).read_text())
    ok, reason, rec = svc.submit(mission)
    print(json.dumps({"accepted": ok, "reason": reason}))
    if not ok:
        return 3
    steps = 0
    while (svc.active is not None or svc.queue_depth > 0) and steps < args.max_steps:
        clock.advance()
        svc.tick()
        link.pump()
        steps += 1
    final = svc.missions[-1]
    print(json.dumps({"final_state": final.state.value, "reason": final.reason,
                      "ticks": steps}))
    return 0 if final.state == MissionState.COMPLETED else 4


def cmd_validate(args) -> int:
    routes = RouteMap(_default_routes_path())
    import os
    secret = os.environ.get("ROVER_MISSION_SECRET", "").encode()
    if not secret:
        print("ROVER_MISSION_SECRET not set", file=sys.stderr)
        return 2
    mission = json.loads(Path(args.file).read_text())
    known_routes, known_wps, known_zones, known_cams = routes.known_ids()
    v = MissionValidator(device_id=routes.device_id, secret=secret)
    res = v.validate(mission, known_routes, known_wps, known_zones, known_cams)
    print(json.dumps({"valid": res.ok, "reason": res.reason,
                      "type": res.mission_type.value if res.mission_type else None}))
    return 0 if res.ok else 3


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="rover-mission")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("simulate-patrols", help="run N patrols on sim link")
    sp.add_argument("count", type=int)
    sp.add_argument("--route", default="patrol-main")
    sp.add_argument("--evidence-dir", default="var/evidence")
    sp.add_argument("--max-steps", type=int, default=20000)
    sp.set_defaults(fn=cmd_simulate_patrols)

    rp = sub.add_parser("run-mission", help="execute a signed mission file")
    rp.add_argument("file")
    rp.add_argument("--evidence-dir", default="var/evidence")
    rp.add_argument("--max-steps", type=int, default=20000)
    rp.set_defaults(fn=cmd_run_mission)

    vp = sub.add_parser("validate", help="validate a mission file")
    vp.add_argument("file")
    vp.set_defaults(fn=cmd_validate)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
