"""GLUE-01 acceptance: device->collector->reducer->2 subscribers.
Covers dedup, bad creds, zone binding, staleness, scoped delivery,
latency measurement, trace ids."""
import hashlib
import hmac
import json

import pytest

from vertical_slice import Collector, Denied, DeviceKey, Reducer

SECRET = b"puck-secret"


def signed(device_id="puck-a", seq=1, event_id="evt-1", **over):
    ev = {"device_id": device_id, "event_id": event_id, "seq": seq,
          "kind": "cabinet_door", "observed_at": "2026-11-08T00:00:00Z",
          "observed_epoch": 1000.0, "data": {"open": True}}
    ev.update(over)
    body = json.dumps({k: v for k, v in ev.items()},
                      sort_keys=True).encode()
    ev["sig"] = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
    return ev


@pytest.fixture
def rig():
    keys = {"puck-a": DeviceKey("puck-a", "rack-01", SECRET)}
    col = Collector(keys)
    red = Reducer()
    admin = red.subscribe("admin-1", "admin", set())
    scoped = red.subscribe("resp-1", "responder", {"inc-9"})
    return col, red, admin, scoped


def deliver(col, red, raw):
    obs = col.ingest(raw)
    return red.reduce(obs)


def test_end_to_end_two_subscribers(rig):
    col, red, admin, scoped = rig
    # unscoped zone telemetry -> both subscribers receive
    assert deliver(col, red, signed()) == "reduced"
    assert len(admin.queue) == 1 and len(scoped.queue) == 1
    obs = admin.queue[0]
    assert obs["device_id"] == "puck-a"
    assert obs["zone_id"] == "rack-01"          # server-side binding
    assert obs["provenance"]["trust"] == "hardware_signed"
    assert obs["trace_id"]                       # provenance trace


def test_duplicate_suppressed(rig):
    col, red, admin, _ = rig
    deliver(col, red, signed())
    assert deliver(col, red, signed()) == "duplicate_suppressed"
    assert len(admin.queue) == 1                # no double delivery


def test_bad_credentials_rejected(rig):
    col, red, admin, _ = rig
    bad = signed()
    bad["sig"] = "0" * 64
    with pytest.raises(Denied):
        col.ingest(bad)
    with pytest.raises(Denied):
        col.ingest(signed(device_id="ghost"))
    assert admin.queue == []


def test_zone_from_key_not_claim(rig):
    col, red, admin, _ = rig
    # attacker claims a different zone in payload — server uses key zone
    obs = col.ingest(signed(zone_id="prod-vault"))
    red.reduce(obs)
    assert admin.queue[0]["zone_id"] == "rack-01"


def test_staleness_visible(rig):
    col, red, _, _ = rig
    now = [1000.0]
    red.clock = lambda: now[0]
    deliver(col, red, signed())
    assert not red.is_stale("puck-a")
    now[0] += 60                                # 60s silence
    assert red.is_stale("puck-a")
    assert "puck-a" in red.delivery_report()["stale_devices"]


def test_incident_scoped_delivery(rig):
    col, red, admin, scoped = rig
    # incident-linked observation only reaches scoped subscriber
    obs = col.ingest(signed(event_id="evt-inc", incident_id="inc-9"))
    red.reduce(obs)
    assert len(scoped.queue) == 1
    # observation for inc-2 -> scoped(resp on inc-9) does NOT get it
    obs2 = col.ingest(signed(event_id="evt-inc2", incident_id="inc-2"))
    red.reduce(obs2)
    assert len(scoped.queue) == 1
    assert len(admin.queue) == 2                # admin sees all


def test_latency_measured(rig):
    col, red, _, _ = rig
    now = [2000.0]
    col.clock = lambda: now[0]
    deliver(col, red, signed(observed_epoch=1999.5))  # 500ms old
    rep = red.delivery_report()
    assert rep["latency_ms_p50"] == pytest.approx(500.0, abs=1)
