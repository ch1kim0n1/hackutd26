import json
import time
from datetime import datetime, timedelta, timezone

import pytest

from correlator import (
    Correlator,
    Inventory,
    NormKind,
    NormalizedObservation,
    Source,
    adapt_kismet_record,
    adapt_puck_event,
)

INV = Inventory({"SENTINEL-CORP": {"02:aa:bb:cc:dd:01"}})
T0 = datetime(2026, 11, 7, 20, 0, 0, tzinfo=timezone.utc)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def wifi(zone="rack-01", bssid="02:aa:bb:cc:dd:99", ssid="SENTINEL-CORP",
         src="puck-a-01", t=0, rssi=-60):
    dt = T0 + timedelta(seconds=t)
    return adapt_puck_event({
        "schema_version": 1, "event_id": f"e-wifi-{t}-{bssid[-2:]}",
        "device_id": src, "seq": t + 1, "observed_at": iso(dt),
        "kind": "wifi_ap_seen", "zone_id": zone,
        "data": {"ssid": ssid, "bssid": bssid, "channel": 6,
                 "rssi_dbm": rssi, "source_id": src},
    })


def cabinet(zone="cabinet-01", contact="open", authorized=False,
            maint=False, t=30):
    dt = T0 + timedelta(seconds=t)
    return adapt_puck_event({
        "schema_version": 1, "event_id": f"e-cab-{t}",
        "device_id": "puck-b-01", "seq": 1, "observed_at": iso(dt),
        "kind": f"cabinet_contact_{contact}", "zone_id": zone,
        "data": {"contact": contact, "authorized": authorized,
                 "maintenance_window": maint},
    })


# ---------- RF01 ----------

def test_rf01_needs_two_scans():
    c = Correlator(INV)
    assert c.ingest(wifi(t=0)) == []
    alerts = c.ingest(wifi(t=10))
    assert len(alerts) == 1 and alerts[0].rule_id == "RF01"
    assert alerts[0].severity == "medium"
    assert "unexpected BSSID" in alerts[0].summary


def test_rf01_known_bssid_no_alert():
    c = Correlator(INV)
    c.ingest(wifi(bssid="02:AA:BB:CC:DD:01", t=0))
    c.ingest(wifi(bssid="02:AA:BB:CC:DD:01", t=10))
    assert c.alerts == []


def test_rf01_unknown_ssid_no_alert():
    c = Correlator(INV)
    c.ingest(wifi(ssid="RANDOM-Guest", t=0))
    c.ingest(wifi(ssid="RANDOM-Guest", t=10))
    assert c.alerts == []  # unknown SSID != known-SSID anomaly


def test_rf01_dedup_counts_but_rules_see_scans():
    c = Correlator(INV, dedup_window_s=30)
    c.ingest(wifi(t=0))
    c.ingest(wifi(t=5))   # dedup-window repeat, still a distinct scan
    assert c.dedup_stats["duplicates"] == 1
    assert any(a.rule_id == "RF01" for a in c.alerts)


# ---------- PHY01 ----------

def test_phy01_unauthorized_open_alerts():
    c = Correlator(INV)
    alerts = c.ingest(cabinet(authorized=False))
    assert len(alerts) == 1 and alerts[0].rule_id == "PHY01"
    assert alerts[0].severity == "high"


def test_phy01_authorized_maintenance_suppressed():
    c = Correlator(INV)
    # approved maintenance: authorized=true -> recorded, NO alert
    assert c.ingest(cabinet(authorized=True, maint=True)) == []
    assert c.alerts == []
    # and therefore no CORR01 either (acceptance: no false breach claim)
    c.ingest(wifi(t=0)); c.ingest(wifi(t=10))
    assert not any(a.rule_id in ("PHY01", "CORR01") for a in c.alerts)


# ---------- CORR01 ----------

def test_corr01_rf_plus_cabinet_same_zone():
    c = Correlator(INV)
    c.ingest(wifi(zone="rack-01", t=0))
    c.ingest(wifi(zone="rack-01", t=10))
    alerts = c.ingest(cabinet(zone="rack-01", authorized=False, t=30))
    rules = {a.rule_id for a in alerts} | {a.rule_id for a in c.alerts}
    assert "RF01" in rules and "PHY01" in rules and "CORR01" in rules
    inc = c.incidents[-1]
    assert inc.zone_id == "rack-01"
    assert "medium" in inc.confidence
    assert inc.alternatives and inc.unknowns  # honest uncertainty


def test_corr01_requires_same_zone():
    c = Correlator(INV)
    c.ingest(wifi(zone="rack-01", t=0)); c.ingest(wifi(zone="rack-01", t=10))
    c.ingest(cabinet(zone="lobby", authorized=False, t=30))
    assert not any(a.rule_id == "CORR01" for a in c.alerts)


# ---------- adapters ----------

def test_kismet_adapter_normalizes():
    rec = {
        "kismet.device.base": {
            "mac": "02:AA:BB:CC:DD:99",
            "last_beaconed_time": "1762540800",
        },
        "kismet.device.base.dot11.device": {
            "dot11.device": "SENTINEL-CORP",
            "dot11.channel": "6",
            "dot11.signal": "-55",
        },
    }
    obs = adapt_kismet_record(rec, zone_id="rack-01")
    assert obs.kind == NormKind.WIFI_AP_SEEN
    assert obs.source.value == "kismet"
    assert obs.data["bssid"] == "02:aa:bb:cc:dd:99"
    assert obs.data["rssi_dbm"] == -55
    assert obs.data["channel"] == 6


def test_puck_event_adapter_roundtrip():
    ev = {
        "schema_version": 1, "event_id": "evt-1", "device_id": "puck-b-01",
        "seq": 7, "observed_at": "2026-11-07T20:00:30Z",
        "kind": "cabinet_contact_open", "zone_id": "cabinet-01",
        "data": {"contact": "open", "authorized": False},
    }
    obs = adapt_puck_event(ev)
    assert obs.kind == NormKind.CABINET_CONTACT_OPEN
    assert obs.receiver_id == "puck-b-01"
    assert adapt_puck_event({"kind": "device_health"}) is None


# ---------- end-to-end demo flow ----------

def test_demo_flow_two_scans_plus_cabinet():
    """docs/10 demo: unknown BSSID on known SSID x2 + cabinet open ->
    RF01 + PHY01 + CORR01 + incident candidate."""
    c = Correlator(INV)
    for t in (0, 8):
        c.ingest(wifi(t=t))
    c.ingest(cabinet(zone="rack-01", t=20, authorized=False))
    rules = [a.rule_id for a in c.alerts]
    assert rules.count("RF01") == 1  # cooldown dedups refires
    assert "PHY01" in rules and "CORR01" in rules
    assert len(c.incidents) == 1
    assert set(c.incidents[0].evidence) >= set(
        c.alerts[-1].observation_ids)
