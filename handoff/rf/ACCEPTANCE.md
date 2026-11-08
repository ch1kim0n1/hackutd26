# RF subsystem — acceptance evidence index (#40)

Maps issue #40 "verify subsystem acceptance and engineering handoff"
criteria to merged work.

## Delivered (merged PRs)

| Issue | PR | Package | Tests | Status |
|---|---|---|---|---|
| #13 Sensor pucks | #59 | `sensors/` | 13 pytest | PARTIAL — host core + ESP-IDF skeletons, no radio HW |
| #14 Kismet correlator | #60 | `sensors/correlator/` | 11 pytest + fixture replay | PARTIAL — adapters tested on fixtures, no live Kismet |
| #15 SDR waterfall | #61 | `sensors/sdr/` | 10 pytest | PARTIAL — synthetic/recorded IQ only, no RTL-SDR |

## Acceptance criteria status

- [x] Interfaces match `docs/03-ROBOTICS-RF.md` + `docs/04` — event
  schema, HMAC auth, dedup, RF01/PHY01/CORR01 rules implemented
- [x] Failure/reconnect/authorization exercised — collector staleness,
  maintenance suppression, BLE enrolled-only filtering, bad-sig reject
- [x] Evidence quality labeled — LIVE/RECORDED/SYNTHETIC provenance,
  `is_measurement:false` on synthetic, `source_mode` warnings
- [ ] Real Kismet capture / ESP32 puck radio / RTL-SDR IQ — BLOCKED
  (no SDR hardware, no live Kismet, no ESP32 radios here)
- [ ] Correlator on live multi-source feed — needs deployed pucks
- [ ] Joint review — pending

## Reproduce tests

```sh
cd sensors && PYTHONPATH=src python3 -m pytest tests/ -q          # 13
cd sensors/correlator && PYTHONPATH=src python3 -m pytest tests/ -q  # 11
cd sensors/sdr && PYTHONPATH=src python3 -m pytest tests/ -q        # 10
python3 -m sdr_waterfall --source synthetic --seconds 5           # demo
```
