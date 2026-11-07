"""Surveyed floor-plan routes — waypoint whitelist for navigation.

The rover may ONLY navigate to waypoints defined here (docs/03: "Known
office floor plan and marked waypoints ... NOT arbitrary SLAM"). Coordinates
are millimetres in the surveyed map frame; tag_id binds an AprilTag to the
spot for localization correction.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

from .models import Route, Waypoint, Zone


class RouteMap:
    def __init__(self, path: str | Path):
        data = json.loads(Path(path).read_text())
        self.device_id = data.get("device_id", "rover-01")
        self.home_waypoint_id = data.get("home_waypoint_id", "")

        self.waypoints: Dict[str, Waypoint] = {}
        self.zones: Dict[str, Zone] = {}
        self.routes: Dict[str, Route] = {}

        for z in data.get("zones", []):
            zone = Zone(id=z["id"], name=z.get("name", z["id"]),
                        bounds=z.get("bounds", {}))
            for w in z.get("waypoints", []):
                wp = Waypoint(
                    id=w["id"], zone_id=z["id"],
                    x_mm=float(w["x_mm"]), y_mm=float(w["y_mm"]),
                    tag_id=w.get("tag_id"),
                    capture=bool(w.get("capture", False)),
                    rescan=bool(w.get("rescan", False)),
                    dwell_ms=int(w.get("dwell_ms", 0)),
                )
                self.waypoints[wp.id] = wp
                zone.waypoints.append(wp)
            self.zones[zone.id] = zone

        for r in data.get("routes", []):
            route = Route(id=r["id"], name=r.get("name", r["id"]),
                          waypoint_ids=list(r["waypoint_ids"]),
                          laps=int(r.get("laps", 1)))
            self.routes[route.id] = route

    def waypoint(self, waypoint_id: str) -> Optional[Waypoint]:
        return self.waypoints.get(waypoint_id)

    def route(self, route_id: str) -> Optional[Route]:
        return self.routes.get(route_id)

    def home(self) -> Optional[Waypoint]:
        return self.waypoints.get(self.home_waypoint_id)

    def known_ids(self):
        return (
            set(self.routes),
            set(self.waypoints),
            set(self.zones),
            {"cam-mast"},  # camera ids are fixed mounts, not surveyed points
        )
