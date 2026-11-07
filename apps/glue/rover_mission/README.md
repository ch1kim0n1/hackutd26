# GLUE-03 Nemotron->rover mission + protected evidence (#50)

Orchestrator: proposal -> approval-bound PolicyGate (TTL, target-bound)
-> Gateway command -> RoverSim (surveyed waypoints only, AprilTag detect)
-> photo evidence (sha256+ts+zone, synthetic-labeled) -> EvidenceVault
(short-lived refs) -> IncidentUpdater.

Fail-closed: no approval, expired approval, unsurveyed waypoint,
approval/target mismatch all denied before any motion.

## Tests
`PYTHONPATH=src python3 -m pytest tests/ -q` -> 6 passed

## NOT done
RoverSim is kinematic sim; real ESP32/Pi stack pending #39/#41;
no real camera/image; depends on unmerged branches.
