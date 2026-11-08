import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from datacenter import DataCenterSim, scenarios  # noqa: E402
from datacenter.publisher import verify_observation  # noqa: E402

ENVELOPE_KEYS = {"schema_version", "event_id", "device_id", "seq",
                 "observed_at", "kind", "zone_id", "data"}
# kinds that should only appear when a scenario injects something
ANOMALY_KINDS = {"config_drift"}
# fields that would leak ground truth into Nemotron-visible telemetry
LABEL_KEYS = {"label", "attack", "scenario", "ground_truth", "expect",
              "is_attack", "verdict", "suspicious"}


def kinds_of(obs):
    out = {}
    for o in obs:
        out[o["kind"]] = out.get(o["kind"], 0) + 1
    return out


def test_all_scenarios_run_and_envelope_valid():
    for name in scenarios.SCENARIO_SCRIPTS:
        res = scenarios.run_scenario(name, ticks=40, seed=11)
        assert res["observations"], name
        for o in res["observations"]:
            assert set(o.keys()) <= ENVELOPE_KEYS | {"signature"}
            assert o["schema_version"] == 1
            assert o["event_id"].startswith("evt-")
        assert res["ground_truth"]["scenario"] == name


def test_baseline_has_no_anomalies():
    res = scenarios.run_scenario("baseline", ticks=60, seed=3)
    obs = res["observations"]
    kinds = kinds_of(obs)
    assert "config_drift" not in kinds
    for o in obs:
        if o["kind"] == "service_inventory":
            assert o["data"]["unexpected"] == []
        if o["kind"] == "device_health":
            assert o["data"]["status"] == "ok"
    # benign traffic may exist but must be ordinary flow records
    for o in obs:
        if o["kind"] == "network_flow":
            assert o["data"]["bytes"] < 1024 * 1024


def test_node_offline_scenario():
    res = scenarios.run_scenario("node_offline", ticks=70, seed=5)
    obs = res["observations"]
    sensor = [o for o in obs if o["device_id"] == "vpi-sensor-01"]
    assert any(o["kind"] == "device_health"
               and o["data"].get("status") == "fault" for o in sensor)
    # recovery: revive emits ok + recovered flag
    assert any(o["kind"] == "device_health"
               and o["data"].get("recovered") is True for o in sensor)
    # while dead (ticks 21-49), the node emits no heartbeats at all
    dead_hb = [o for o in sensor
               if o["data"].get("note") == "heartbeat"
               and "2026-11-07T18:00:21.000Z" <= o["observed_at"]
               < "2026-11-07T18:00:50.000Z"]
    assert not dead_hb, "dead node must be silent"
    # heartbeats resume only after revive at tick 45 (next due ~tick 50)
    resumed = [o for o in sensor
               if o["data"].get("note") == "heartbeat"
               and o["observed_at"] >= "2026-11-07T18:00:50.000Z"]
    assert resumed, "expected heartbeats after revive"


def test_unexpected_service_scenario():
    res = scenarios.run_scenario("unexpected_service", ticks=70, seed=5)
    inv = [o for o in res["observations"]
           if o["kind"] == "service_inventory"
           and o["device_id"] == "vpi-compute-01"]
    flagged = [o for o in inv if o["data"]["unexpected"]]
    assert flagged, "expected inventory with unexpected listener"
    assert flagged[0]["data"]["unexpected"] == [
        {"name": "minerd", "port": 3333, "proto": "tcp"}]
    # healed by end of run: last inventory is clean
    assert inv[-1]["data"]["unexpected"] == []


def test_config_drift_scenario():
    res = scenarios.run_scenario("config_drift", ticks=70, seed=5)
    drift = [o for o in res["observations"] if o["kind"] == "config_drift"]
    assert drift
    opened = [o for o in drift if o["data"]["resolved"] is False]
    closed = [o for o in drift if o["data"]["resolved"] is True]
    assert opened and opened[0]["data"]["key"] == "ssh_password_auth"
    assert closed
    # drift also degrades health heartbeats
    deg = [o for o in res["observations"]
           if o["device_id"] == "vpi-mgmt-01"
           and o["kind"] == "device_health"
           and o["data"].get("status") == "degraded"]
    assert deg


def test_suspicious_traffic_scenario_is_objective():
    res = scenarios.run_scenario("suspicious_traffic", ticks=50, seed=5)
    flows = [o for o in res["observations"] if o["kind"] == "network_flow"]
    assert len(flows) >= 2
    # suspicious shapes present as raw facts
    assert any(f["data"].get("distinct_dst_ports", 0) >= 8 for f in flows)
    assert any(f["data"].get("bytes", 0) >= 64 * 1024 * 1024 for f in flows)
    # no verdict/label fields anywhere in telemetry data
    for o in res["observations"]:
        assert not (LABEL_KEYS & set(o["data"].keys())), o["data"].keys()


def test_benign_high_cpu_has_no_anomaly_signals():
    res = scenarios.run_scenario("benign_high_cpu", ticks=60, seed=5)
    obs = res["observations"]
    rm = [o for o in obs if o["kind"] == "resource_metric"
          and o["device_id"] == "vpi-compute-01"]
    assert rm and max(o["data"]["cpu_pct"] for o in rm) >= 90.0
    # nothing an incident rule could fire on
    assert not any(o["kind"] == "config_drift" for o in obs)
    for o in obs:
        if o["kind"] == "service_inventory":
            assert o["data"]["unexpected"] == []
        if o["kind"] == "device_health":
            assert o["data"]["status"] in {"ok"}
        if o["kind"] == "network_flow":
            assert o["data"]["bytes"] < 64 * 1024 * 1024
            assert o["data"].get("distinct_dst_ports", 0) < 8


def test_ground_truth_separate_from_observations():
    res = scenarios.run_scenario("node_offline", ticks=50, seed=5)
    truth = res["ground_truth"]
    assert truth["label"] == "attack" and truth["expect"] == "incident"
    assert truth["injections"]
    # labels reference event ids but are NOT inside observation payloads
    blob = json.dumps(res["observations"])
    assert '"label"' not in blob and '"attack"' not in blob
    assert '"scenario"' not in blob
    # every event_id listed in truth exists in the stream
    all_ids = {o["event_id"] for o in res["observations"]}
    for ids in truth["event_ids"].values():
        assert set(ids) <= all_ids


def test_scenario_determinism():
    a = scenarios.run_scenario("unexpected_service", ticks=50, seed=9)
    b = scenarios.run_scenario("unexpected_service", ticks=50, seed=9)
    assert a["observations"] == b["observations"]


def test_publish_signs_and_topics(tmp_path):
    sent = []
    from datacenter import SimPublisher
    pub = SimPublisher(sim=DataCenterSim(seed=0),
                       secrets={n: f"k-{n}".encode() for n in
                                ("vpi-compute-01", "vpi-network-01",
                                 "vpi-sensor-01", "vpi-mgmt-01")},
                       transport=lambda o, t: sent.append((o, t)))
    res = scenarios.run_scenario("config_drift", ticks=40, seed=4)
    n = scenarios.publish_observations(res["observations"], pub)
    assert n == len(res["observations"]) == len(sent)
    for obs, topic in sent:
        assert topic == f"sentinel/v1/{obs['device_id']}/telemetry"
        assert verify_observation(obs, pub.secrets[obs["device_id"]])


def test_write_artifacts_separates_labels(tmp_path):
    res = scenarios.run_scenario("baseline", ticks=30, seed=2)
    scenarios.write_artifacts({"baseline": res}, tmp_path)
    obs_file = tmp_path / "baseline" / "observations.jsonl"
    truth_file = tmp_path / "ground_truth.json"
    assert obs_file.exists() and truth_file.exists()
    obs_blob = obs_file.read_text()
    assert '"label"' not in obs_blob
    truth = json.loads(truth_file.read_text())
    assert truth["baseline"]["label"] == "benign"
