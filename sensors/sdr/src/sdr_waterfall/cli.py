"""CLI: capture/replay waterfall or build channel-activity view.

  waterfall --synthetic --rows 32 --fft 1024 --out wf.json
  waterfall --file iq.cf32 --rate 2.4e6 --center 433.92e6 --rows 16
  activity observations.jsonl --zone rack-01 --out activity.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .channel_activity import channel_activity
from .iq_sources import FileIqSource, HardwareUnavailable, SyntheticIqSource
from .models import SourceMode
from .receivers import Receiver, UnsupportedBand, load_receivers
from .waterfall import capture_waterfall


def _receiver_cfg(path: str) -> dict[str, Receiver]:
    return load_receivers(path)


def main() -> int:
    ap = argparse.ArgumentParser(prog="sdr-waterfall")
    sub = ap.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("waterfall")
    w.add_argument("--synthetic", action="store_true")
    w.add_argument("--file", default=None)
    w.add_argument("--rate", type=float, default=2.4e6)
    w.add_argument("--center", type=float, default=433.92e6)
    w.add_argument("--fft", type=int, default=1024)
    w.add_argument("--rows", type=int, default=32)
    w.add_argument("--window", default="hann")
    w.add_argument("--receiver-config",
                   default=str(Path(__file__).parents[2] / "config" / "receivers.json"))
    w.add_argument("--receiver", default=None,
                   help="enforce capability check against named receiver")
    w.add_argument("--out", default=None)

    a = sub.add_parser("activity")
    a.add_argument("observations", help="JSONL of canonical events")
    a.add_argument("--zone", required=True)
    a.add_argument("--mode", default="live",
                   choices=[m.value for m in SourceMode])
    a.add_argument("--out", default=None)

    args = ap.parse_args()

    if args.cmd == "waterfall":
        if args.file:
            src = FileIqSource(args.file, args.rate, args.center)
        elif args.synthetic:
            src = SyntheticIqSource(args.rate, args.center)
        else:
            print("specify --synthetic or --file", file=sys.stderr)
            return 2
        # capability guard when a named receiver is given
        if args.receiver:
            recvs = _receiver_cfg(args.receiver_config)
            try:
                recvs[args.receiver].check_band(args.center, args.rate)
            except (KeyError, UnsupportedBand) as e:
                print(json.dumps({"error": str(e)}))
                return 3
        wf = capture_waterfall(src, fft_size=args.fft, rows=args.rows,
                               window_type=args.window)
        text = json.dumps(wf.to_dict())
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(text + "\n")
        print(text[:400] + "...")
        return 0

    # activity
    obs = []
    for line in Path(args.observations).read_text().splitlines():
        line = line.strip()
        if line:
            obs.append(json.loads(line))
    act = channel_activity(obs, args.zone, SourceMode(args.mode))
    text = json.dumps(act.to_dict(), indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
