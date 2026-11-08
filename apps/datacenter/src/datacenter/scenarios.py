"""Controlled data-center scenarios + ground-truth labels.

Each scenario drives DataCenterSim through a scripted injection timeline
and returns the emitted canonical observations — the ONLY data that may
be published toward SpacetimeDB/Nemotron.

Ground truth (which injections were attacks vs benign, and when) is
returned separately and written to ``ground_truth.json`` — it is NEVER
merged into observations and NEVER published. Observations carry
objective telemetry fields only; classification is the correlator's job.

Usage:
    python -m datacenter.scenarios [--out DIR] [--ticks N] [--publish]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable, Optional

from .publisher import SimPublisher, sign_observation
from .simulator import DataCenterSim

DEFAULT_TICKS = 90
ARTIFACTS = Path(__file__).resolve().parents[2] / "artifacts"


# ---------------------------------------------------------------------------
# Scenario scripts — each returns (sim, ground_truth dict)
# ---------------------------------------------------------------------------

def _baseline(sim: DataCenterSim, ticks: int) -> list[dict]:
    return _run(sim, ticks)


def _node_offline(sim: DataCenterSim, ticks: int) -> list[dict]:
    """vpi-sensor-01 loses power mid-run, stays dead, then recovers."""
    obs = _run(sim, 20)
    sim.kill("vpi-sensor-01")
    obs += _run(sim, 25)                 # fault + silence -> STALE window
    sim.revive("vpi-sensor-01")
    return obs + _run(sim, ticks - 45)


def _unexpected_service(sim: DataCenterSim, ticks: int) -> list[dict]:
    """Rogue listener appears on the compute node, later removed."""
    obs = _run(sim, 20)
    sim.inject_service("vpi-compute-01", "minerd", 3333,
                       version="xmrig/6.21")
    obs += _run(sim, 30)
    sim.heal_service("vpi-compute-01", 3333)
    return obs + _run(sim, ticks - 50)


def _config_drift(sim: DataCenterSim, ticks: int) -> list[dict]:
    """ssh_password_auth flips on; later restored (recovery)."""
    obs = _run(sim, 20)
    sim.inject_drift("vpi-mgmt-01", "ssh_password_auth", True)
    obs += _run(sim, 30)
    sim.heal_drift("vpi-mgmt-01", "ssh_password_auth")
    return obs + _run(sim, ticks - 50)


def _suspicious_traffic(sim: DataCenterSim, ticks: int) -> list[dict]:
    """Sensor node reports a port-scan summary + an oversized egress flow.
    Fields are objective flow facts only — no verdict labels."""
    obs = _run(sim, 20)
    sim.emit_flow(
        "vpi-sensor-01",
        src="198.51.100.66", dst="192.0.2.101", proto="tcp",
        distinct_dst_ports=32, packets=1280, bytes=51200,
        duration_s=4.2, direction="ingress",
        flags={"syn": 1280, "rst": 1216},
    )
    sim.emit_flow(
        "vpi-compute-01",
        src="192.0.2.101", dst="203.0.113.99", proto="tcp",
        dst_port=4444, packets=98000, bytes=67108864,
        duration_s=95.0, direction="egress",
    )
    return obs + _run(sim, ticks - 20)


def _benign_high_cpu(sim: DataCenterSim, ticks: int) -> list[dict]:
    """Sustained 96% CPU on the compute node — legitimate batch job.
    Must produce resource_metric telemetry and NO anomaly signals."""
    obs = _run(sim, 10)
    sim.set_load("vpi-compute-01", 96.0)
    obs += _run(sim, ticks - 10)
    sim.clear_load("vpi-compute-01")
    return obs


SCENARIO_SCRIPTS: dict[str, Callable[[DataCenterSim, int], list[dict]]] = {
    "baseline": _baseline,
    "node_offline": _node_offline,
    "unexpected_service": _unexpected_service,
    "config_drift": _config_drift,
    "suspicious_traffic": _suspicious_traffic,
    "benign_high_cpu": _benign_high_cpu,
}

# Ground-truth labels: evaluation-only metadata. attack scenarios map to
# the incident rules the correlator is expected to raise; benign maps to
# "no incident". Never embedded in observation payloads.
GROUND_TRUTH = {
    "baseline": {"label": "benign", "expect": "no_incidents"},
    "node_offline": {
        "label": "attack",
        "expect": "incident",
        "injections": [
            {"tick": 20, "node": "vpi-sensor-01", "action": "kill"},
            {"tick": 45, "node": "vpi-sensor-01", "action": "revive"},
        ],
    },
    "unexpected_service": {
        "label": "attack",
        "expect": "incident",
        "injections": [
            {"tick": 20, "node": "vpi-compute-01",
             "action": "inject_service", "detail": "minerd:3333"},
            {"tick": 50, "node": "vpi-compute-01",
             "action": "heal_service", "detail": "minerd:3333"},
        ],
    },
    "config_drift": {
        "label": "attack",
        "expect": "incident",
        "injections": [
            {"tick": 20, "node": "vpi-mgmt-01",
             "action": "inject_drift",
             "detail": "ssh_password_auth=true"},
            {"tick": 50, "node": "vpi-mgmt-01",
             "action": "heal_drift",
             "detail": "ssh_password_auth"},
        ],
    },
    "suspicious_traffic": {
        "label": "attack",
        "expect": "incident",
        "injections": [
            {"tick": 20, "node": "vpi-sensor-01",
             "action": "emit_flow", "detail": "port-scan summary"},
            {"tick": 20, "node": "vpi-compute-01",
             "action": "emit_flow", "detail": "64MiB egress :4444"},
        ],
    },
    "benign_high_cpu": {
        "label": "benign",
        "expect": "no_incidents",
        "injections": [
            {"tick": 10, "node": "vpi-compute-01",
             "action": "set_load", "detail": "cpu_pct=96"},
        ],
    },
}


def _run(sim: DataCenterSim, ticks: int) -> list[dict]:
    out: list[dict] = []
    for _ in range(ticks):
        out.extend(sim.tick())
    return out


def run_scenario(name: str, ticks: int = DEFAULT_TICKS,
                 seed: int = 7) -> dict:
    """Run one scenario; returns observations + separate ground truth."""
    if name not in SCENARIO_SCRIPTS:
        raise KeyError(f"unknown scenario {name!r}; "
                       f"choices: {sorted(SCENARIO_SCRIPTS)}")
    sim = DataCenterSim(seed=seed)
    obs = SCENARIO_SCRIPTS[name](sim, ticks)
    # scripts always end with a tick() flush, so _pending is empty here;
    # tick() return values are the canonical stream (drain() would repeat).
    truth = dict(GROUND_TRUTH[name])
    truth["scenario"] = name
    truth["seed"] = seed
    truth["ticks"] = ticks
    truth["observation_count"] = len(obs)
    # event ids of interest for eval alignment (labels stay out of obs)
    truth["event_ids"] = {
        kind: [o["event_id"] for o in obs if o["kind"] == kind]
        for kind in sorted({o["kind"] for o in obs})
    }
    return {"observations": obs, "ground_truth": truth}


def _secrets_from_env() -> dict[str, bytes]:
    """Per-device HMAC secrets from DC_HMAC_KEYS JSON env
    ({device_id: secret}) — values are used verbatim as UTF-8, exactly
    like the gateway's GATEWAY_DEVICE_HMAC_KEYS (createHmac key = the
    env string itself). Do NOT hex-decode: parity with
    verifyDeviceSignature requires identical key bytes."""
    import os
    raw = os.environ.get("DC_HMAC_KEYS", "")
    if not raw:
        return {}
    return {k: v.encode() for k, v in json.loads(raw).items()}


def publish_observations(obs: list[dict],
                         publisher: Optional[SimPublisher] = None,
                         seq_offset: Optional[dict] = None) -> int:
    """Sign + publish observations through SimPublisher (MQTT env contract).
    Mutates obs dicts in place to add `signature` — call after artifacts
    are written if unsigned artifacts are wanted.

    Each scenario runs on a fresh sim, so per-device `seq` restarts at 1.
    `seq_offset` (device_id -> last published seq) lets consecutive
    scenario batches keep seq monotonic per device against the gateway's
    stale-seq check; signatures are computed after the rewrite. The
    offset is a per-batch BASE — it must not be updated per observation
    or it compounds."""
    pub = publisher or SimPublisher(sim=DataCenterSim(seed=0),
                                    secrets=_secrets_from_env())
    offset = seq_offset if seq_offset is not None else {}
    base = {did: offset.get(did, 0) for did in {o["device_id"] for o in obs}}
    top: dict = {}
    sent = 0
    for o in obs:
        did = o["device_id"]
        o["seq"] = int(o["seq"]) + base[did]
        secret = pub.secrets.get(did)
        if secret:
            o["signature"] = sign_observation(o, secret)
        pub.transport(o, f"sentinel/v1/{did}/telemetry")
        if int(o["seq"]) > top.get(did, 0):
            top[did] = int(o["seq"])
        sent += 1
    offset.update(top)
    return sent


def write_artifacts(results: dict[str, dict], out_root: Path) -> None:
    """Write per-scenario observations.jsonl + a shared ground_truth.json.
    The two files are deliberately separate artifacts."""
    out_root.mkdir(parents=True, exist_ok=True)
    labels = {}
    for name, res in results.items():
        d = out_root / name
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "observations.jsonl", "w") as fh:
            for o in res["observations"]:
                fh.write(json.dumps(o, separators=(",", ":")) + "\n")
        labels[name] = res["ground_truth"]
    (out_root / "ground_truth.json").write_text(
        json.dumps(labels, indent=2, sort_keys=True))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ARTIFACTS)
    ap.add_argument("--ticks", type=int, default=DEFAULT_TICKS)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--scenario", choices=sorted(SCENARIO_SCRIPTS),
                    help="run one scenario (default: all)")
    ap.add_argument("--publish", action="store_true",
                    help="sign + publish observations over MQTT env")
    ap.add_argument("--seq-base", type=int, default=0,
                    help="minimum seq offset per device (re-run against a "
                         "database whose lastSeq is already advanced)")
    args = ap.parse_args()

    names = [args.scenario] if args.scenario else sorted(SCENARIO_SCRIPTS)
    results = {}
    for name in names:
        res = run_scenario(name, ticks=args.ticks, seed=args.seed)
        results[name] = res
        kinds = {}
        for o in res["observations"]:
            kinds[o["kind"]] = kinds.get(o["kind"], 0) + 1
        print(f"{name}: {len(res['observations'])} obs {kinds} "
              f"label={res['ground_truth']['label']}")

    write_artifacts(results, args.out)
    print(f"artifacts -> {args.out} "
          f"(observations.jsonl per scenario + ground_truth.json)")

    if args.publish:
        import time
        # One publisher = one MQTT client/session for the whole run;
        # per-scenario clients with the same client_id would fight over
        # the broker session and reorder/drop QoS-1 publishes.
        pub = SimPublisher(sim=DataCenterSim(seed=0),
                           secrets=_secrets_from_env())
        total = 0
        offset: dict = {did: args.seq_base for name in names
                        for did in {o["device_id"]
                                    for o in results[name]["observations"]}}
        for name in names:
            total += publish_observations(results[name]["observations"],
                                          publisher=pub, seq_offset=offset)
        # QoS-1 publishes flush asynchronously — give the broker a beat
        # before the process exits.
        time.sleep(2.0)
        print(f"published {total} signed observations")


if __name__ == "__main__":
    main()
