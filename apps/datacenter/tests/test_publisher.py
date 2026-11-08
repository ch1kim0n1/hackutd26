import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from datacenter import DataCenterSim, SimPublisher, sign_observation, verify_observation


def test_sign_verify_roundtrip():
    obs = {"schema_version": 1, "event_id": "evt-x", "device_id": "d1",
           "seq": 1, "observed_at": "2026-11-07T18:00:00.000Z",
           "kind": "device_health", "zone_id": "rack-01", "data": {"a": 1}}
    sig = sign_observation(obs, b"sec")
    signed = dict(obs, signature=sig)
    assert verify_observation(signed, b"sec")
    assert not verify_observation(signed, b"wrong")
    assert not verify_observation(obs, b"sec")  # unsigned fails


def test_signature_ignores_extra_fields():
    """Signature covers only the 8 signed fields; extras don't break it."""
    obs = {"schema_version": 1, "event_id": "evt-x", "device_id": "d1",
           "seq": 1, "observed_at": "2026-11-07T18:00:00.000Z",
           "kind": "device_health", "zone_id": "rack-01", "data": {"a": 1},
           "extra_field": "ignored"}
    sig = sign_observation(obs, b"sec")
    assert sig == sign_observation({k: obs[k] for k in
                                    ("schema_version", "event_id", "device_id",
                                     "seq", "observed_at", "kind",
                                     "zone_id", "data")}, b"sec")


def test_sim_publisher_signs_and_topics():
    sent = []
    secrets = {n: f"key-{n}".encode() for n in
               ("vpi-compute-01", "vpi-network-01", "vpi-sensor-01",
                "vpi-mgmt-01")}
    pub = SimPublisher(sim=DataCenterSim(seed=3), secrets=secrets,
                       transport=lambda o, t: sent.append((o, t)))
    pub.run(30)
    assert pub.published > 0
    for obs, topic in sent:
        assert topic == f"sentinel/v1/{obs['device_id']}/telemetry"
        assert verify_observation(obs, secrets[obs["device_id"]])


def test_unsigned_when_no_secret():
    sent = []
    pub = SimPublisher(sim=DataCenterSim(seed=1), secrets={},
                       transport=lambda o, t: sent.append(o))
    pub.run(10)
    assert sent and all("signature" not in o for o in sent)


def test_per_node_streams_independent():
    """Each node's seq is independent; killing one doesn't affect others."""
    sent = []
    pub = SimPublisher(sim=DataCenterSim(seed=5), secrets={},
                       transport=lambda o, t: sent.append(o))
    pub.run(40)
    by_node = {}
    for o in sent:
        by_node.setdefault(o["device_id"], []).append(o["seq"])
    assert len(by_node) == 4
    for seqs in by_node.values():
        assert seqs == sorted(seqs)


def test_console_transport_shape(capsys):
    from datacenter.publisher import _console_transport
    t = _console_transport()
    t({"a": 1}, "sentinel/v1/x/telemetry")
    out = json.loads(capsys.readouterr().out.strip())
    assert out["topic"] == "sentinel/v1/x/telemetry"
    assert out["obs"] == {"a": 1}


def test_seq_persists_across_restart(tmp_path):
    """Restarted publisher must not re-emit low seqs (replay reject)."""
    state = str(tmp_path / "seq.json")
    sent1 = []
    p1 = SimPublisher(sim=DataCenterSim(seed=9), secrets={},
                      transport=lambda o, t: sent1.append(o),
                      state_file=state)
    p1.run(20)
    max_by_node = {}
    for o in sent1:
        max_by_node[o["device_id"]] = max(
            max_by_node.get(o["device_id"], 0), o["seq"])
    sent2 = []
    p2 = SimPublisher(sim=DataCenterSim(seed=9), secrets={},
                      transport=lambda o, t: sent2.append(o),
                      state_file=state)
    p2.run(10)
    for o in sent2:
        assert o["seq"] > max_by_node[o["device_id"]]
