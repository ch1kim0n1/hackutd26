# Motor Safety Test Report — TEMPLATE (not yet executed)

> Status: **NOT RUN.** Fill in after H02/H03 bring-up gates. Attach scope
> screenshots and multimeter photos to `test-evidence/`.

Date: ____________  Operator: ____________  Firmware hash: ____________

## Stall current measurement (per motor channel)

| Channel | Motor | Stall current (A) | Driver limit (A) | Fuse | Pass? |
|---|---|---|---|---|---|
| Left outer | | | TB6612 1.2 A cont / 3.2 A peak | | |
| Left inner | | | | | |
| Right inner | | | | | |
| Right outer | | | | | |

Method: wheels locked, 50% PWM for ≤2 s, clamp meter in series. If any channel
exceeds driver continuous rating → swap to BTS7960-class driver before continuing
(conflict C-3).

## E-stop response

| Test | Commanded speed | Time to full stop (ms) | VM after stop (V) | Pass? |
|---|---|---|---|---|
| E-stop press during drive | | | | |
| E-stop press at stall attempt | | | | |
| Pi USB disconnect (watchdog) | | | | |
| ToF obstacle approach | | | | |

## Thermal / electrical

- TB6612 case temp after 5 min capped drive: ____ °C
- 5 V Pi rail min voltage during drive (scope): ____ V
- Battery voltage after 30 min patrol: ____ V
- Estimated runtime at measured average current: ____ min

## Faults observed

| Time | Fault code | Telemetry ref | Resolution |
|---|---|---|---|
| | | | |

Sign-off: ____________  (hardware owner)   Date: ____________
