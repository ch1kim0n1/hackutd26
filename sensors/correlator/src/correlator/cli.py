"""Replay newline-delimited JSON observations -> alerts/incidents.

Usage: PYTHONPATH=src python3 -m correlator.cli fixture.jsonl --inventory inv.json
Emits a JSON summary; exit 0 always (analysis tool, not a gate)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters import adapt_kismet_record, adapt_puck_event, adapt_stream
from .correlator import Correlator
from .inventory import Inventory
from .models import Source


def _norm_line(obj: dict, zone: str):
    """Dispatch on payload shape: canonical event vs kismet record."""
    if "kind" in obj and "device_id" in obj:
        return adapt_puck_event(obj, zone_id=zone or None)
    if "kismet.device.base" in obj:
        return adapt_kismet_record(obj, zone_id=zone or "unknown",
                                   receiver_id="kismet-01")
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("fixture", help="JSONL of canonical events or kismet records")
    ap.add_argument("--inventory", default=None)
    ap.add_argument("--zone", default="")
    ap.add_argument("--out", default=None, help="write incident summary JSON")
    args = ap.parse_args()

    inv = Inventory.load(args.inventory) if args.inventory else Inventory()
    corr = Correlator(inv)
    zone = args.zone
    for line in Path(args.fixture).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        obs = _norm_line(obj, zone)
        if obs:
            corr.ingest(obs)

    summary = {
        "observations": corr.dedup_stats,
        "alerts": [
            {"rule_id": a.rule_id, "severity": a.severity, "state": a.state,
             "zone_id": a.zone_id, "summary": a.summary,
             "observation_ids": a.observation_ids,
             "evidence_quality": a.evidence_quality}
            for a in corr.alerts
        ],
        "incident_candidates": [i.to_dict() for i in corr.incidents],
    }
    text = json.dumps(summary, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
