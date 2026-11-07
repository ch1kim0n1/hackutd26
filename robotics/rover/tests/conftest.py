import json
import time

import pytest

from rover_mission.camera import SyntheticCamera
from rover_mission.localization import NoopDetector
from rover_mission.models import MissionType
from rover_mission.motor_link import SimulatedLink
from rover_mission.routes import RouteMap
from rover_mission.service import RoverService, ServiceConfig, make_signed_mission
from rover_mission.telemetry import ConsolePublisher

SECRET = b"test-secret"
DEVICE = "rover-01"


class FakeClock:
    def __init__(self, start: float = 1_700_000_000.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


ROUTES_JSON = {
    "device_id": DEVICE,
    "home_waypoint_id": "wp-home",
    "zones": [
        {
            "id": "zone-a", "name": "Zone A", "bounds": {},
            "waypoints": [
                {"id": "wp-home", "x_mm": 0, "y_mm": 0, "tag_id": 0},
                {"id": "wp-a", "x_mm": 500, "y_mm": 0, "tag_id": 1},
                {"id": "wp-b", "x_mm": 500, "y_mm": 500, "tag_id": 2,
                 "capture": True, "dwell_ms": 100},
                {"id": "wp-c", "x_mm": 0, "y_mm": 500, "tag_id": 3},
            ],
        },
        {
            "id": "zone-b", "name": "Zone B", "bounds": {},
            "waypoints": [
                {"id": "wp-far", "x_mm": 5000, "y_mm": 5000, "tag_id": 4},
            ],
        },
    ],
    "routes": [
        {"id": "loop-a", "name": "A loop", "laps": 1,
         "waypoint_ids": ["wp-a", "wp-b", "wp-c"]},
        {"id": "loop-a2", "name": "A loop x2", "laps": 2,
         "waypoint_ids": ["wp-a", "wp-b"]},
    ],
}


@pytest.fixture
def route_map(tmp_path):
    p = tmp_path / "routes.json"
    p.write_text(json.dumps(ROUTES_JSON))
    return RouteMap(p)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def link():
    lk = SimulatedLink(tick_s=0.1)
    lk.connect()
    return lk


@pytest.fixture
def service(route_map, link, clock, tmp_path):
    return RoverService(
        route_map, link,
        camera=SyntheticCamera(), detector=NoopDetector(),
        publisher=ConsolePublisher(stream=open(tmp_path / "events.jsonl", "w")),
        config=ServiceConfig(device_id=DEVICE, secret=SECRET,
                             evidence_dir=str(tmp_path / "evidence")),
        clock=clock,
    )


def signed(mtype, mission_id, command_id, clock, expires_s=3600, **fields):
    return make_signed_mission(
        device_id=DEVICE, secret=SECRET, mtype=mtype,
        mission_id=mission_id, command_id=command_id,
        expires_at=time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                 time.gmtime(clock.t + expires_s)),
        **fields,
    )


def run_until_done(service, link, clock, max_ticks=20000):
    ticks = 0
    while (service.active is not None or service.queue_depth > 0) \
            and ticks < max_ticks:
        clock.advance(service.cfg.tick_s)
        service.tick()  # pumps the link internally
        ticks += 1
    return ticks
