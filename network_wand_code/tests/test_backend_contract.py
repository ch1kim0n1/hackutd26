"""Wand <-> backend contract tests (issue #117).

The production endpoint network_wand_code/backend/app.py does not exist;
these tests freeze the contract wand.py already speaks and prove the
fake backend honours the same semantics (target retask, ack clearing).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from backend_contract import (
    ContractError, FakeWandBackend, WandCommand, WandReport,
)


def _report(**over):
    body = {
        "wand_id": "wand-01", "rack_id": "", "bssid": "",
        "rssi": -62.5, "mode": "HUNT", "frames_per_s": 12.0,
        "deauths_3s": 0, "ack": False,
    }
    body.update(over)
    return body


# ---------------- request schema ----------------

def test_valid_report_accepted_and_normalized():
    r = WandReport.from_dict(_report(bssid="AA:BB:CC:DD:EE:FF", rssi=None))
    assert r.bssid == "aa:bb:cc:dd:ee:ff"   # lowercased like wand.py expects
    assert r.rssi is None
    assert r.mode == "HUNT"
    assert r.to_dict()["ack"] is False


def test_missing_fields_rejected():
    body = _report()
    del body["frames_per_s"]
    with pytest.raises(ContractError, match="frames_per_s"):
        WandReport.from_dict(body)


def test_bad_mode_and_types_rejected():
    with pytest.raises(ContractError, match="mode"):
        WandReport.from_dict(_report(mode="EXPLODE"))
    with pytest.raises(ContractError):
        WandReport.from_dict(_report(rssi="not-a-number"))
    with pytest.raises(ContractError):
        WandReport.from_dict(_report(deauths_3s="x"))
    with pytest.raises(ContractError):
        WandReport.from_dict(["not", "a", "dict"])


# ---------------- response schema ----------------

def test_command_schema_and_channel_range():
    c = WandCommand.from_dict({"bssid": "AA:BB", "rack_id": "rack-7", "channel": 6})
    assert c.bssid == "aa:bb" and c.channel == 6
    assert WandCommand.from_dict({}).channel == 0          # empty = no channel
    with pytest.raises(ContractError):
        WandCommand.from_dict({"channel": 99})
    with pytest.raises(ContractError):
        WandCommand.from_dict({"channel": "six"})


# ---------------- fake backend semantics ----------------

def test_fake_backend_target_and_ack_flow():
    be = FakeWandBackend()
    # No target yet -> empty command fields, wand keeps current target.
    assert be.handle(_report()) == {"bssid": "", "rack_id": "", "channel": 0}
    # Operator tasks the wand.
    be.set_target("02:11:22:33:44:55", rack_id="rack-3", channel=11)
    resp = be.handle(_report(rssi=-40.0))
    assert resp == {"bssid": "02:11:22:33:44:55", "rack_id": "rack-3", "channel": 11}
    # Alert ack is counted and cleared.
    be.handle(_report(ack=True))
    assert be.acks_cleared == 1
    assert len(be.reports) == 3


def test_fake_backend_rejects_malformed_report():
    be = FakeWandBackend()
    with pytest.raises(ContractError):
        be.handle({"wand_id": "wand-01"})
    assert be.reports == []


def test_contract_covers_every_field_wand_sends():
    # wand.py backend_loop body keys — keep this list in sync.
    body = _report()
    assert set(body) == {
        "wand_id", "rack_id", "bssid", "rssi", "mode",
        "frames_per_s", "deauths_3s", "ack",
    }
    WandReport.from_dict(body)  # must not raise
