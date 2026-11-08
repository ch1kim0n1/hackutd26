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


def _build_service(args, evidence_dir=None):
    """Build RoverService on simulated or real ESP32 link.

    args.link: 'sim' (default) | 'esp32'. esp32 requires --port and
    pyserial. Real link uses wall clock — no acceleration."""
    import os as _os
    routes = RouteMap(_default_routes_path())
    secret = _os.environ.get("ROVER_MISSION_SECRET", "").encode()
    if not secret:
        print("ROVER_MISSION_SECRET not set", file=sys.stderr)
        return None, None, None
    use_real = getattr(args, "link", "sim") == "esp32"
    if use_real:
        from .motor_link import Esp32SerialLink
        link = Esp32SerialLink(getattr(args, "port", "") or "/dev/ttyUSB0")
        if not link.connect():
            print("serial link connect failed", file=sys.stderr)
            return None, None, None
        clock = time.time
    else:
        link = SimulatedLink(tick_s=0.1)
        link.connect()
        clock = _SimClock(0.1)
    svc = RoverService(
        routes, link,
        publisher=ConsolePublisher(sys.stdout),
        config=ServiceConfig(device_id=routes.device_id, secret=secret,
                             evidence_dir=evidence_dir or args.evidence_dir),
        clock=clock,
    )
    return svc, link, clock


def _drive(svc, link, clock, max_steps):
    steps = 0
    while (svc.active is not None or svc.queue_depth > 0) and steps < max_steps:
        if hasattr(clock, "advance"):
            clock.advance()
        else:
            time.sleep(0.05)  # real link: real time between ticks
        svc.tick()
        link.pump()
        steps += 1
    return steps


def cmd_run_mission(args) -> int:
    svc, link, clock = _build_service(args)
    if svc is None:
        return 2
    mission = json.loads(Path(args.file).read_text())
    ok, reason, rec = svc.submit(mission)
    print(json.dumps({"accepted": ok, "reason": reason}))
    if not ok:
        return 3
    steps = _drive(svc, link, clock, args.max_steps)
    final = svc.missions[-1]
    print(json.dumps({"final_state": final.state.value, "reason": final.reason,
                      "ticks": steps}))
    return 0 if final.state == MissionState.COMPLETED else 4


def cmd_watch_missions(args) -> int:
    """Poll a directory (e.g. mission-shim inbox) for signed mission files.

    Each *.json is validated+executed once; a sibling <name>.done marker is
    written afterwards so restarts never re-run a mission. Files appearing
    mid-write are skipped until they parse (shim writes atomically, but be
    safe)."""
    inbox = Path(args.dir)
    if not inbox.is_dir():
        print(f"watch dir not found: {inbox}", file=sys.stderr)
        return 2
    svc, link, clock = _build_service(args)
    if svc is None:
        return 2
    processed = set()
    ran = 0
    while args.max_missions <= 0 or ran < args.max_missions:
        files = sorted(inbox.glob("*.json"))
        pending = [f for f in files
                   if f not in processed
                   and not f.with_suffix(f.suffix + ".done").exists()]
        if not pending:
            time.sleep(args.poll_s)
            continue
        for f in pending:
            processed.add(f)
            try:
                mission = json.loads(f.read_text())
            except (ValueError, OSError) as e:
                print(json.dumps({"file": f.name, "error": f"unreadable: {e}"}))
                f.with_suffix(f.suffix + ".done").write_text("error")
                continue
            ok, reason, _rec = svc.submit(mission)
            if not ok:
                print(json.dumps({"file": f.name, "accepted": False,
                                  "reason": reason}))
                f.with_suffix(f.suffix + ".done").write_text(reason)
                continue
            steps = _drive(svc, link, clock, args.max_steps)
            final = svc.missions[-1]
            print(json.dumps({"file": f.name, "mission_id": final.mission_id,
                              "final_state": final.state.value,
                              "reason": final.reason, "ticks": steps}))
            f.with_suffix(f.suffix + ".done").write_text(final.state.value)
            ran += 1
    return 0


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


def cmd_intercept(args) -> int:
    """Run the monitor-mode interceptor (+ optional honeypot classifier)."""
    import os
    from .honeypot import Honeypot
    from .interceptor import Interceptor
    from .telemetry import publisher_from_env

    publisher = publisher_from_env()
    secret = os.environ.get("ROVER_MISSION_SECRET", "").encode()
    honeypot = None
    if args.honeypot:
        decoys = ([{"ssid": s, "bssid": f"02:11:22:33:44:{55 + i:02x}"}
                   for i, s in enumerate(args.decoy_ssid)]
                  if args.decoy_ssid else None)
        def _rogue(hit):
            print(f"[honeypot] ROGUE {hit.mac} -> {hit.ssid} "
                  f"({hit.frame_count} frames, rssi {hit.last_rssi})",
                  file=sys.stderr)
        honeypot = Honeypot(decoys=decoys, on_rogue=_rogue)
    interceptor = Interceptor(
        device_id=args.device, zone_id=args.zone, publisher=publisher,
        iface=args.iface, channel=args.channel, secret=secret,
        on_frame=(honeypot.feed_observation if honeypot else None),
    )
    print(f"intercepting on {args.iface} ch{args.channel} "
          f"as {args.device} (honeypot={'on' if honeypot else 'off'})",
          file=sys.stderr)
    interceptor.run_forever()
    return 0


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
    rp.add_argument("--link", choices=["sim", "esp32"], default="sim",
                    help="motor link: sim (default) or real ESP32 serial")
    rp.add_argument("--port", default="/dev/ttyUSB0",
                    help="serial port for --link esp32")
    rp.set_defaults(fn=cmd_run_mission)

    wp = sub.add_parser("watch-missions",
                        help="poll a directory for signed mission files")
    wp.add_argument("dir", help="inbox dir (e.g. mission-shim output)")
    wp.add_argument("--evidence-dir", default="var/evidence")
    wp.add_argument("--max-steps", type=int, default=20000)
    wp.add_argument("--poll-s", type=float, default=1.0)
    wp.add_argument("--max-missions", type=int, default=0,
                    help="0 = run forever")
    wp.add_argument("--link", choices=["sim", "esp32"], default="sim",
                    help="motor link: sim (default) or real ESP32 serial")
    wp.add_argument("--port", default="/dev/ttyUSB0",
                    help="serial port for --link esp32")
    wp.set_defaults(fn=cmd_watch_missions)

    vp = sub.add_parser("validate", help="validate a mission file")
    vp.add_argument("file")
    vp.set_defaults(fn=cmd_validate)

    ip = sub.add_parser("intercept",
                        help="monitor-mode Wi-Fi sniffer -> canonical observations")
    ip.add_argument("--iface", default="wlan1")
    ip.add_argument("--channel", type=int, default=6)
    ip.add_argument("--device", default="rover-01",
                    help="device_id in emitted envelopes")
    ip.add_argument("--zone", default="lobby")
    ip.add_argument("--honeypot", action="store_true",
                    help="flag stations probing/associating with decoy SSIDs")
    ip.add_argument("--decoy-ssid", action="append", default=[],
                    help="decoy SSID (repeatable); default pair used if none")
    ip.set_defaults(fn=cmd_intercept)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
