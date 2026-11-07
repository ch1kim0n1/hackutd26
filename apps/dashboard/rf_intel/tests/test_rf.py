"""UX-29 RF intel: heatmap/inventory/series from real scans only."""
import pytest

from rf_intel import RFIntel, RFIntelDenied


@pytest.fixture
def intel():
    return RFIntel()


def scan(intel, aps, prov="LIVE", src="kismet-1"):
    return intel.add_scan(src, aps, prov)


def test_heatmap_only_observed_channels(intel):
    scan(intel, [{"bssid": "aa", "ssid": "X", "channel": 6,
                  "rssi_dbm": -50},
                 {"bssid": "bb", "ssid": "Y", "channel": 6,
                  "rssi_dbm": -70},
                 {"bssid": "cc", "ssid": "Z", "channel": 11,
                  "rssi_dbm": -40}])
    heat = intel.channel_heatmap()
    assert set(heat) == {6, 11}                       # no fabricated ch
    assert heat[6]["count"] == 2
    assert heat[6]["avg_rssi_dbm"] == -60.0
    assert heat[6]["bssid_count"] == 2
    assert heat[6]["provenance"] == ["LIVE"]


def test_bssid_inventory_aggregates(intel):
    scan(intel, [{"bssid": "aa", "ssid": "Corp", "channel": 6,
                  "rssi_dbm": -50}], "LIVE", "esp32-a")
    scan(intel, [{"bssid": "aa", "ssid": "Corp", "channel": 6,
                  "rssi_dbm": -55}], "REPLAY", "kismet-1")
    inv = intel.bssid_inventory()
    assert inv["aa"]["sightings"] == 2
    assert inv["aa"]["sources"] == ["esp32-a", "kismet-1"]
    assert inv["aa"]["provenance"] == ["LIVE", "REPLAY"]


def test_rssi_series_timestamped(intel):
    scan(intel, [{"bssid": "aa", "channel": 6, "rssi_dbm": -50}])
    scan(intel, [{"bssid": "aa", "channel": 6, "rssi_dbm": -48}])
    pts = intel.rssi_series(bssid="aa")
    assert len(pts) == 2 and pts[0]["at"] <= pts[1]["at"]
    assert all("provenance" in p and "source" in p for p in pts)


def test_provenance_enforced(intel):
    with pytest.raises(RFIntelDenied):
        intel.add_scan("x", [], "SYNTHETIC")
    with pytest.raises(RFIntelDenied):
        intel.add_scan("x", [], "LIVE-ISH")


def test_evidence_permission_checked(intel):
    scan(intel, [{"bssid": "aa", "ssid": "X", "channel": 6,
                  "rssi_dbm": -50}])
    # device role denied
    with pytest.raises(RFIntelDenied):
        intel.evidence_for("aa", "device", {"inc-1"})
    # scoped incident enforced
    intel.incident_links["aa"] = "inc-9"
    with pytest.raises(RFIntelDenied, match="scope"):
        intel.evidence_for("aa", "responder", {"inc-1"})
    ok = intel.evidence_for("aa", "responder", {"inc-9"})
    assert ok["bssid"] == "aa" and len(ok["series"]) == 1


def test_empty_state_honest(intel):
    assert intel.channel_heatmap() == {}
    assert intel.bssid_inventory() == {}
    assert intel.rssi_series() == []
