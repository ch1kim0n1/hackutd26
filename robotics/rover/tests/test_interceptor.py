import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rover_mission.interceptor import (
    Interceptor, build_observation, classify_frame, mac_str, ssid_from_tags,
)
from rover_mission.honeypot import Honeypot, RogueHit, DEFAULT_DECOYS


def test_classify_frame_kinds():
    assert classify_frame(0x08) == "wifi_ap_seen"      # beacon
    assert classify_frame(0x04) == "wifi_probe"        # probe request
    assert classify_frame(0x05) == "wifi_ap_seen"      # probe response
    assert classify_frame(0x0B) == "rf_frame_meta"     # auth
    assert classify_frame(0xFF) is None                # data frame


def test_mac_and_ssid_parse():
    assert mac_str(bytes([0x02, 0x11, 0x22, 0x33, 0x44, 0x55])) == \
        "02:11:22:33:44:55"
    tags = bytes([0x00, 0x04]) + b"FREE" + bytes([0x01, 0x08, 0x82])
    assert ssid_from_tags(tags) == "FREE"
    assert ssid_from_tags(b"") == ""


def test_build_observation_signed():
    obs = build_observation("rover-01", "lobby", "wifi_ap_seen",
                            {"ssid": "X"}, 7, secret=b"sec")
    assert obs["device_id"] == "rover-01"
    assert obs["seq"] == 7
    assert obs["signature"]
    # verify signature matches canonical form
    import hashlib, hmac as _h
    body = {k: obs[k] for k in ("schema_version", "event_id", "device_id",
                                "seq", "observed_at", "kind", "zone_id", "data")}
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True)
    assert obs["signature"] == _h.new(b"sec", canon.encode(),
                                      hashlib.sha256).hexdigest()


class FakePublisher:
    def __init__(self):
        self.sent = []
    def publish(self, ev):
        self.sent.append(ev)


def test_interceptor_dedupe_and_seq():
    pub = FakePublisher()
    it = Interceptor("rover-01", "lobby", pub, secret=b"sec")
    obs = build_observation("rover-01", "lobby", "wifi_ap_seen",
                            {"ssid": "X", "bssid": "aa:bb"}, 0)
    # simulate handle_packet internals via _should_emit + seq
    key = "wifi_ap_seen:aa:bb:X"
    assert it._should_emit(key)
    assert not it._should_emit(key)          # deduped within window
    it._seq += 1
    it.publisher.publish(obs)
    assert pub.sent[0]["seq"] == 0
    assert it._seq == 1


def test_honeypot_flags_probe_for_decoy():
    hits = []
    hp = Honeypot(on_rogue=hits.append)
    obs = {"kind": "wifi_probe", "data": {
        "ssid": "FREE-AIRPORT-WIFI", "addr2": "de:ad:be:ef:00:01",
        "rssi_dbm": -55}}
    hit = hp.feed_observation(obs)
    assert hit is not None and hit.mac == "de:ad:be:ef:00:01"
    assert hit.ssid == "FREE-AIRPORT-WIFI"
    assert len(hits) == 1


def test_honeypot_ignores_corp_ssid_and_beacons():
    hp = Honeypot()
    assert hp.feed_observation({"kind": "wifi_probe", "data": {
        "ssid": "MERIDIAN-CORP", "addr2": "aa:bb:cc:dd:ee:01"}}) is None
    # beacon from our own decoy BSSID is not a rogue frame
    assert hp.feed_observation({"kind": "wifi_ap_seen", "data": {
        "bssid": "02:11:22:33:44:55", "ssid": "FREE-AIRPORT-WIFI",
        "addr2": "02:11:22:33:44:55"}}) is None


def test_honeypot_auth_to_decoy_bssid():
    hp = Honeypot()
    obs = {"kind": "rf_frame_meta", "data": {
        "bssid": "02:11:22:33:44:55", "addr2": "ca:fe:00:11:22:33",
        "ssid": "FREE-AIRPORT-WIFI", "rssi_dbm": -60}}
    hit = hp.feed_observation(obs)
    assert hit is not None and hit.mac == "ca:fe:00:11:22:33"


def test_rogue_accumulates():
    hp = Honeypot()
    obs = {"kind": "wifi_probe", "data": {
        "ssid": "GUEST-NO-PASSWORD", "addr2": "11:22:33:44:55:66"}}
    hp.feed_observation(obs)
    hp.feed_observation(obs)
    assert hp.rogues["11:22:33:44:55:66"].frame_count == 2


def test_hostapd_config_shape():
    from rover_mission.honeypot import hostapd_config
    cfg = hostapd_config(DEFAULT_DECOYS, iface="wlan1", channel=6)
    assert "interface=wlan1" in cfg
    assert "ssid=FREE-AIRPORT-WIFI" in cfg
    assert "wpa=0" in cfg  # open lure
    assert cfg.count("bss=") == 2
