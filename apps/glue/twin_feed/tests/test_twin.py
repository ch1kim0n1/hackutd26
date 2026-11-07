"""GLUE-04: unified twin feed — auth, provenance, staleness, scope."""
import pytest

from twin_feed import FeedDenied, TwinFeed


@pytest.fixture
def feed():
    return TwinFeed()


def test_provenance_labeled_and_enforced(feed):
    live = feed.push("rover_pose", "r1", {"x": 1, "y": 2}, "LIVE")
    rep = feed.push("rf_scan", "s1", {"channels": {}}, "REPLAY")
    syn = feed.push("photo", "p1", {"sha": "x"}, "SYNTHETIC")
    assert {live.provenance, rep.provenance, syn.provenance} == \
        {"LIVE", "REPLAY", "SYNTHETIC"}
    with pytest.raises(FeedDenied):
        feed.push("chat", "c1", {}, "MADE_UP")


def test_scoped_subscription_no_leak(feed):
    feed.push("timeline", "t1", {"incident_id": "inc-1", "ev": "a"})
    feed.push("timeline", "t2", {"incident_id": "inc-2", "ev": "b"})
    feed.push("rover_pose", "r1", {"x": 0})          # unscoped infra
    s_resp = feed.subscribe("resp", "responder", {"inc-1"})
    out = feed.stream(s_resp)
    incs = {i.payload.get("incident_id") for i in out
            if i.payload.get("incident_id")}
    assert incs == {"inc-1"}                        # no inc-2 leak
    assert any(i.kind == "rover_pose" for i in out)  # infra visible
    with pytest.raises(FeedDenied):
        feed.stream("bogus-sub")


def test_staleness_marked_at_read(feed):
    now = [1000.0]
    feed.clock = lambda: now[0]
    feed.push("rover_pose", "r1", {"x": 1})
    s = feed.subscribe("a", "admin", set())
    assert feed.stream(s)[0].stale is False
    now[0] += 60
    assert feed.stream(s)[0].stale is True          # honestly flagged


def test_rf_only_real_scans(feed):
    # no scan pushed -> empty; fabricated spectrum impossible
    assert feed.rf_scans() == []
    feed.push("rf_scan", "s1", {"bssid": "aa", "rssi": -60})
    assert len(feed.rf_scans()) == 1


def test_incident_context_aggregates(feed):
    feed.push("timeline", "t1", {"incident_id": "inc-1", "ev": "created"})
    feed.push("scope", "sc1", {"incident_id": "inc-1", "cia": "c"})
    feed.push("chat", "m1", {"incident_id": "inc-1", "body": "hi"})
    feed.push("photo", "ph1", {"incident_id": "inc-1", "sha": "z"})
    ctx = feed.incident_context("inc-1")
    assert len(ctx["timeline"]) == 1 and len(ctx["chat"]) == 1
    assert len(ctx["scope"]) == 1 and len(ctx["photos"]) == 1
    assert feed.incident_context("inc-2")["chat"] == []


def test_since_cursor_reconnect(feed):
    for i in range(4):
        feed.push("chat", f"m{i}", {"incident_id": "inc-1"})
    s = feed.subscribe("a", "admin", set())
    assert len(feed.stream(s, since=2)) == 2          # items 3,4 only
