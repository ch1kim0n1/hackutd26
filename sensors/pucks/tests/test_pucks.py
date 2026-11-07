import time

import pytest

from puck_core import (
    CabinetPuck,
    Collector,
    EventKind,
    HealthStatus,
    Inventory,
    MaintenanceWindow,
    BlePuck,
    Observation,
    WifiPuck,
    sign,
    verify,
)

SECRET = b"test-secret-0123456789abcdef"
OTHER_SECRET = b"wrong-secret"


def make_inventory(with_window: bool = False) -> Inventory:
    inv = Inventory(
        known_bssids={"SENTINEL-CORP": {"02:aa:bb:cc:dd:01"}},
        enrolled_beacons={"aa:bb:cc:dd:ee:01", "11111111-2222-3333-4444-555555555555"},
        maintenance_windows=[
            MaintenanceWindow("cabinet-01", "2026-01-01T00:00:00Z",
                              "2026-12-31T23:59:59Z", "operator-jane")
        ] if with_window else [],
    )
    return inv


class FakeClock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


@pytest.fixture
def clock():
    return FakeClock()


# ---------- auth ----------

def test_signature_roundtrip_and_tamper(clock):
    p = WifiPuck("puck-a-01", "rack-01", SECRET, make_inventory(), clock=clock)
    [obs] = p.scan([{"ssid": "X", "bssid": "02:aa:bb:cc:dd:01",
                     "channel": 6, "rssi_dbm": -50}])
    assert obs.signature
    raw = obs.to_dict()
    raw["data"]["rssi_dbm"] = -30  # tamper
    bad = Observation.from_dict(raw)
    assert bad.signature and not verify(SECRET, bad)


# ---------- puck A ----------

def test_wifi_known_and_unknown_bssid(clock):
    inv = make_inventory()
    p = WifiPuck("puck-a-01", "rack-01", SECRET, inv, clock=clock)
    evs = p.scan([
        {"ssid": "SENTINEL-CORP", "bssid": "02:AA:BB:CC:DD:01",
         "channel": 6, "rssi_dbm": -50},
        {"ssid": "SENTINEL-CORP", "bssid": "02:AA:BB:CC:DD:99",
         "channel": 6, "rssi_dbm": -60},
        {"ssid": "SENTINEL-CORP", "bssid": "02:aa:bb:cc:dd:99",
         "channel": 6, "rssi_dbm": -60},  # dup within window -> deduped
    ])
    assert len(evs) == 2  # third deduped
    known, unknown = evs
    assert known.data["known_bssid"] is True and known.data["suspicion"] == "none"
    assert unknown.data["known_bssid"] is False
    assert unknown.data["suspicion"] == "first_unknown_bssid"


def test_wifi_unknown_bssid_streak_flags_suspicion(clock):
    p = WifiPuck("puck-a-01", "rack-01", SECRET, make_inventory(), clock=clock)
    rogue = {"ssid": "SENTINEL-CORP", "bssid": "02:aa:bb:cc:dd:99",
             "channel": 6, "rssi_dbm": -60}
    p.scan([rogue])
    clock.advance(6.0)
    [e2] = p.scan([rogue])
    assert e2.data["unknown_bssid_streak"] == 2
    assert e2.data["suspicion"] == "unknown_bssid_on_known_ssid"


def test_wifi_seq_monotonic(clock):
    p = WifiPuck("puck-a-01", "rack-01", SECRET, make_inventory(), clock=clock)
    seqs = [o.seq for o in p.events]
    p.scan([{"ssid": "A", "bssid": "01:00:00:00:00:01",
             "channel": 1, "rssi_dbm": -70}])
    p.scan([{"ssid": "B", "bssid": "01:00:00:00:00:02",
             "channel": 11, "rssi_dbm": -80}])
    assert [o.seq for o in p.events] == sorted(o.seq for o in p.events)
    assert p.events[-1].seq == len(p.events)


# ---------- puck B ----------

def _feed(puck, levels, clock):
    out = []
    for lv in levels:
        out.extend(puck.sample(lv))
        clock.advance(0.01)
    return out


def test_cabinet_debounce_rejects_bounce(clock):
    p = CabinetPuck("puck-b-01", "cabinet-01", SECRET, make_inventory(),
                    debounce_s=0.05, clock=clock)
    # start closed, brief open bounce < debounce, returns closed -> no events
    _feed(p, [True] * 5 + [False, True, False, True] + [True] * 10, clock)
    assert p.events == []


def test_cabinet_open_outside_maintenance_is_unauthorized(clock):
    p = CabinetPuck("puck-b-01", "cabinet-01", SECRET, make_inventory(),
                    debounce_s=0.02, clock=clock)
    _feed(p, [True] * 3, clock)
    evs = _feed(p, [False] * 10, clock)  # open, debounce passes
    assert len(evs) == 1
    e = evs[0]
    assert e.kind == EventKind.CABINET_CONTACT_OPEN
    assert e.data["authorized"] is False
    assert e.data["contact"] == "open"


def test_cabinet_open_inside_window_authorized(clock):
    inv = Inventory(
        known_bssids={}, enrolled_beacons=set(),
        maintenance_windows=[MaintenanceWindow(
            "cabinet-01", "2020-01-01T00:00:00Z", "2099-12-31T23:59:59Z")])
    # NOTE: observed_at is real UTC; window spans all realistic test times
    p = CabinetPuck("puck-b-01", "cabinet-01", SECRET, inv,
                    debounce_s=0.02, clock=clock)
    _feed(p, [True] * 3, clock)
    evs = _feed(p, [False] * 10, clock)
    assert evs[0].data["authorized"] is True
    assert evs[0].data["maintenance_window"] is True


def test_cabinet_close_event(clock):
    p = CabinetPuck("puck-b-01", "cabinet-01", SECRET, make_inventory(),
                    debounce_s=0.02, clock=clock)
    _feed(p, [True] * 3 + [False] * 10, clock)
    evs = _feed(p, [True] * 10, clock)
    assert len(evs) == 1 and evs[0].kind == EventKind.CABINET_CONTACT_CLOSED
    assert evs[0].data["authorized"] is True


# ---------- puck C ----------

def test_ble_enrolled_emits_unenrolled_dropped(clock):
    p = BlePuck("puck-c-01", "lab-bench", SECRET, make_inventory(), clock=clock)
    evs = p.observe("AA:BB:CC:DD:EE:01", -55, service_uuid=None)
    assert len(evs) == 1
    assert evs[0].kind == EventKind.BLE_BEACON_SEEN
    assert evs[0].data["enrolled"] is True
    # non-enrolled: nothing emitted, counted, no identifiers retained
    n0 = len(p.events)
    assert p.observe("11:22:33:44:55:66", -40) == []
    assert p.observe(None, -40, service_uuid="deadbeef-0000-0000-0000-000000000000") == []
    assert len(p.events) == n0
    assert p.dropped_unenrolled == 2


def test_ble_service_uuid_enrollment_and_dedup(clock):
    p = BlePuck("puck-c-01", "lab-bench", SECRET, make_inventory(), clock=clock)
    [e1] = p.observe(None, -60,
                     service_uuid="11111111-2222-3333-4444-555555555555")
    assert e1.data["beacon_key"] == "11111111-2222-3333-4444-555555555555"
    clock.advance(2.0)
    assert p.observe(None, -61,
                     service_uuid="11111111-2222-3333-4444-555555555555") == []  # dedup
    clock.advance(11.0)
    assert len(p.observe(None, -62,
                         service_uuid="11111111-2222-3333-4444-555555555555")) == 1


# ---------- collector ----------

def _collector(clock):
    c = Collector(stale_after_s=10.0, clock=clock)
    c.register("puck-a-01", "puck-a", "rack-01", SECRET)
    c.register("puck-b-01", "puck-b", "cabinet-01", SECRET)
    c.register("puck-c-01", "puck-c", "lab-bench", SECRET)
    return c


def test_collector_accepts_valid_signed_events(clock):
    c = _collector(clock)
    a = WifiPuck("puck-a-01", "rack-01", SECRET, make_inventory(), clock=clock)
    b = CabinetPuck("puck-b-01", "cabinet-01", SECRET, make_inventory(), clock=clock)
    cc = BlePuck("puck-c-01", "lab-bench", SECRET, make_inventory(), clock=clock)
    a.scan([{"ssid": "S", "bssid": "02:aa:bb:cc:dd:01",
             "channel": 6, "rssi_dbm": -50}])
    _feed(b, [True] * 3 + [False] * 10, clock)
    cc.observe("aa:bb:cc:dd:ee:01", -55)
    for obs in a.events + b.events + cc.events:
        res = c.ingest(obs.to_dict())
        assert res.ok, res.reason
    assert len(c.accepted) == len(a.events) + len(b.events) + len(cc.events)


def test_collector_rejects_forgery_replay_kind_zone(clock):
    c = _collector(clock)
    a = WifiPuck("puck-a-01", "rack-01", SECRET, make_inventory(), clock=clock)
    a.scan([{"ssid": "S", "bssid": "02:aa:bb:cc:dd:01",
             "channel": 6, "rssi_dbm": -50}])
    good = a.events[0].to_dict()
    assert c.ingest(good).ok
    # replay same seq
    assert c.ingest(good).reason == "stale_or_replayed_seq"
    # tampered signature
    bad = dict(good); bad["signature"] = "0" * 64
    bad["seq"] = 99
    assert c.ingest(bad).reason == "bad_signature"
    # unknown device
    u = dict(good); u["device_id"] = "puck-z-99"; u["seq"] = 100
    u_no_sig = {k: v for k, v in u.items() if k != "signature"}
    u["signature"] = sign(SECRET, Observation.from_dict(u_no_sig))
    assert c.ingest(u).reason == "unknown_device"
    # wrong kind for device type
    b = CabinetPuck("puck-b-01", "cabinet-01", SECRET, make_inventory(), clock=clock)
    _feed(b, [True] * 3 + [False] * 10, clock)
    assert c.ingest(b.events[-1].to_dict()).ok
    # BLE event sent AS puck-a device -> kind not allowed
    cc = BlePuck("puck-c-01", "lab-bench", SECRET, make_inventory(), clock=clock)
    [be] = cc.observe("aa:bb:cc:dd:ee:01", -55)
    forged = be.to_dict(); forged["device_id"] = "puck-a-01"
    forged["zone_id"] = "rack-01"
    forged_no_sig = {k: v for k, v in forged.items() if k != "signature"}
    forged["signature"] = sign(SECRET, Observation.from_dict(forged_no_sig))
    forged["seq"] = 500
    assert c.ingest(forged).reason == "kind_not_allowed_for_device"


def test_collector_stale_and_offline_visibility(clock):
    c = _collector(clock)
    a = WifiPuck("puck-a-01", "rack-01", SECRET, make_inventory(), clock=clock)
    a.scan([{"ssid": "S", "bssid": "02:aa:bb:cc:dd:01",
             "channel": 6, "rssi_dbm": -50}])
    c.ingest(a.events[0].to_dict())
    clock.advance(15.0)  # > stale_after
    evs = c.refresh_health()
    assert c.devices["puck-a-01"].status == HealthStatus.STALE
    assert any(e.kind == EventKind.DEVICE_OFFLINE for e in evs)
    clock.advance(60.0)  # > 4x stale -> offline
    c.refresh_health()
    assert c.devices["puck-a-01"].status == HealthStatus.OFFLINE
    assert c.devices["puck-b-01"].status == HealthStatus.OFFLINE  # never seen
