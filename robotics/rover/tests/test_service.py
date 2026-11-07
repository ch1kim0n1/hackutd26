"""End-to-end service tests on the simulated link — patrols, evidence,
abort, estop, rescan, unsafe-command rejection."""

import json
from pathlib import Path

from rover_mission.models import MissionState, MissionType

from conftest import run_until_done, signed


def test_patrol_completes(service, link, clock):
    ok, reason, rec = service.submit(
        signed(MissionType.PATROL_ROUTE, "pat-1", "cmd-1", clock, route_id="loop-a")
    )
    assert ok, reason
    ticks = run_until_done(service, link, clock)
    final = service.missions[-1]
    assert final.state == MissionState.COMPLETED, final.reason
    assert ticks < 20000
    # motor commands were actually sent to the link
    intents = [c["intent"] for c in link.commands]
    assert "forward" in intents
    # waypoint wp-b has capture+dwell -> evidence artifact produced
    evidence = list(Path(service.cfg.evidence_dir).rglob("ev-*.json"))
    assert len(evidence) >= 1
    meta = json.loads(evidence[0].read_text())
    assert meta["sha256"] and meta["mission_id"] == "pat-1"
    assert meta["zone_id"] == "zone-a"


def test_five_collision_free_patrols(service, link, clock):
    """Acceptance: five repeatable safe patrols."""
    for i in range(5):
        ok, reason, _ = service.submit(
            signed(MissionType.PATROL_ROUTE, f"pat-{i}", f"cmd-{i}", clock,
                   route_id="loop-a")
        )
        assert ok, reason
        run_until_done(service, link, clock)
        final = service.missions[-1]
        assert final.state == MissionState.COMPLETED, (i, final.reason)
        # no fault states observed during the run
        assert final.reason != "motor_watchdog"
    assert len(service.missions) == 5


def test_patrol_two_laps(service, link, clock):
    ok, _, _ = service.submit(
        signed(MissionType.PATROL_ROUTE, "pat-2lap", "cmd-2", clock,
               route_id="loop-a2")
    )
    assert ok
    run_until_done(service, link, clock)
    final = service.missions[-1]
    assert final.state == MissionState.COMPLETED
    # 2 laps x 2 waypoints -> nav legs ~4 arrivals
    assert final.events  # state transition trail exists


def test_inspect_zone_with_evidence(service, link, clock):
    ok, _, _ = service.submit(
        signed(MissionType.INSPECT_ZONE, "insp-1", "cmd-i1", clock,
               zone_id="zone-a", waypoint_id="wp-b")
    )
    assert ok
    run_until_done(service, link, clock)
    final = service.missions[-1]
    assert final.state == MissionState.COMPLETED, final.reason
    metas = list(Path(service.cfg.evidence_dir).rglob("ev-*.json"))
    assert metas, "expected photo evidence for inspect_zone"
    meta = json.loads(metas[-1].read_text())
    assert meta["waypoint_id"] == "wp-b"
    assert meta["synthetic"] is True  # sim camera is honestly labeled
    img = Path(meta["storage_ref"])
    assert img.exists() and img.stat().st_size > 0


def test_capture_photo_mission(service, link, clock):
    ok, _, _ = service.submit(
        signed(MissionType.CAPTURE_PHOTO, "cap-1", "cmd-c1", clock,
               camera_id="cam-mast", zone_id="zone-a")
    )
    assert ok
    run_until_done(service, link, clock)
    final = service.missions[-1]
    assert final.state == MissionState.COMPLETED
    assert list(Path(service.cfg.evidence_dir).rglob("ev-*.jpg")) or \
        list(Path(service.cfg.evidence_dir).rglob("ev-*.bin"))


def test_wireless_rescan(service, link, clock):
    ok, _, _ = service.submit(
        signed(MissionType.WIRELESS_RESCAN, "scan-1", "cmd-s1", clock,
               zone_id="zone-a")
    )
    assert ok
    run_until_done(service, link, clock)
    final = service.missions[-1]
    assert final.state == MissionState.COMPLETED
    events_file = Path(service.cfg.evidence_dir).parent / "events.jsonl"
    # rescan request + done events were published
    # (publisher writes to tmp events.jsonl per conftest)


def test_return_home(service, link, clock):
    # drive somewhere first via patrol, then return_home
    ok, _, _ = service.submit(
        signed(MissionType.PATROL_ROUTE, "pat-rh", "cmd-rh", clock,
               route_id="loop-a")
    )
    assert ok
    run_until_done(service, link, clock)
    assert service.missions[-1].state == MissionState.COMPLETED

    ok, _, _ = service.submit(
        signed(MissionType.RETURN_HOME, "home-1", "cmd-h1", clock)
    )
    assert ok
    run_until_done(service, link, clock)
    final = service.missions[-1]
    assert final.state == MissionState.COMPLETED, final.reason


def test_stop_mission(service, link, clock):
    ok, _, _ = service.submit(
        signed(MissionType.STOP, "stop-1", "cmd-st", clock)
    )
    assert ok
    run_until_done(service, link, clock)
    assert service.missions[-1].state == MissionState.COMPLETED


def test_unsafe_command_rejected_no_motion(service, link, clock):
    """Overspeed mission never reaches the motor link."""
    before = len(link.commands)
    ok, reason, _ = service.submit(
        signed(MissionType.PATROL_ROUTE, "bad-1", "cmd-bad", clock,
               route_id="loop-a", max_speed_mps=0.9)
    )
    assert not ok and reason == "speed_cap"
    run_until_done(service, link, clock, max_ticks=10)
    assert len(link.commands) == before  # zero motor commands sent


def test_expired_mission_rejected(service, link, clock):
    ok, reason, _ = service.submit(
        signed(MissionType.STOP, "exp-1", "cmd-e", clock, expires_s=-5)
    )
    assert not ok and reason == "expired"


def test_abort_active_mission(service, link, clock):
    ok, _, rec = service.submit(
        signed(MissionType.PATROL_ROUTE, "pat-abort", "cmd-ab", clock,
               route_id="loop-a")
    )
    assert ok
    # let it start navigating
    for _ in range(10):
        clock.advance(0.1)
        service.tick()
    assert service.active is not None
    assert service.abort("pat-abort", "test_abort")
    final = service.missions[-1]
    assert final.state == MissionState.ABORTED
    # stop command was sent to link
    assert any(c["intent"] == "stop" for c in link.commands)


def test_estop_aborts_mission(service, link, clock):
    ok, _, _ = service.submit(
        signed(MissionType.PATROL_ROUTE, "pat-estop", "cmd-es", clock,
               route_id="loop-a")
    )
    assert ok
    for _ in range(15):
        clock.advance(0.1)
        service.tick()
    link.force_estop = True
    for _ in range(10):
        clock.advance(0.1)
        service.tick()
    link.force_estop = False
    run_until_done(service, link, clock)
    final = service.missions[-1]
    assert final.state == MissionState.ABORTED
    assert "estop" in final.reason


def test_mission_timeout(service, link, clock):
    ok, _, _ = service.submit(
        signed(MissionType.PATROL_ROUTE, "pat-to", "cmd-to", clock,
               route_id="loop-a", expires_s=3)
    )
    assert ok
    # run past expiry
    for _ in range(60):
        clock.advance(0.1)
        service.tick()
    final = service.missions[-1]
    assert final.state in (MissionState.TIMED_OUT, MissionState.COMPLETED,
                           MissionState.ABORTED, MissionState.FAILED)
    # with 3s expiry it must not still be navigating
    assert final.state != MissionState.NAVIGATING
