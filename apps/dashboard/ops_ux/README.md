# UX-32 stress-first incident ops UX composition (#32)

`ux_spec.py`: layout contract — 6 regions (queue/doc/scope/chat/
admin/approvals), per-role VISIBILITY matrix, <=60s responder task
path (4 steps x 15s budget), validate_layout(), A11Y_REQUIREMENTS.
Visibility is UX-only — server-side enforcement stays with #23.

## Tests
`python3 -m pytest test_ux.py -q` -> 5 passed

## NOT done
Composition contract only — actual React layout/components pending
#28 twin + design; 60-second untrained-operator test needs live UI.
