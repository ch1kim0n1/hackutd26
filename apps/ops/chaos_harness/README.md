# OPS-37 chaos/integration evidence harness (#37)

`chaos_harness.py`: 8 adversarial scenarios (event_replay,
bad_credentials, lab_compromise, private_subscription, chat_injection,
model_injection, actuator_verify_fail, safety_estop) vs injectable
backends -> PASS/FAIL/NOT_RUN + JSON/MD artifacts via
`write_artifacts()`. Missing backend = NOT_RUN, never faked.

## Tests
`PYTHONPATH=src python3 -m pytest tests/ -q` -> 5 passed

## NOT done
Scenario doubles are in-memory; real W01-W05 evidence needs deployed
stack; artifacts dir ready for committed evidence.
