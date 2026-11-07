# GLUE-06 Winstead W01-W05 cross-system acceptance (#53)

`acceptance.py`: AcceptanceRunner executes every docs/06 W-item against
injectable backends; records PASS/FAIL/**NOT_RUN** with evidence.
Missing backend -> NOT_RUN (never faked); simulated passes labeled
SIMULATED; report states `deployment_acceptance: NOT CLAIMED`.
Includes lab-pivot check (W01a: hostile lab principal reaches zero
services) and condensed W02-W05 cross-checks.

## Tests
`PYTHONPATH=src python3 -m pytest tests/ -q` -> 4 passed

## NOT done
Requires real deployed backends for REAL-mode acceptance; current
run is SIMULATED + NOT_RUN — does not claim Winstead readiness.
