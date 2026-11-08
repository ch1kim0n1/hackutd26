# contracts/rover — shared mission-contract test vectors

JSON fixtures consumed identically by all three rover stacks' test suites
(issue #115, spec: `docs/14-ROVER-MISSION-CONTRACT.md`):

- `missions.json` — common mission → module `commandJson` → signed rover
  mission → autonomy directive, for every mission type including the
  device-local `wireless_rescan` and the lossy `rover_form_lossy` cases.
- `telemetry.json` — rover `_emit` payloads and autonomy `{pose,mode}`
  reports → `sentinel.rover.telemetry` common objects.
- `evidence.json` — rover sidecar/`EvidenceRef` shapes →
  `sentinel.rover.evidence` common objects + module evidence row, including
  the rescan-marker rejection case.

Consumers:

- `robotics/rover/tests/test_common_contract.py`, `test_autonomy_parity.py`
- `autonomy/tests/test_mission_map.py`
- `services/mission-shim/test/common.test.ts`

Any change to a fixture is a contract change — update the spec and all
three implementations in the same PR.
