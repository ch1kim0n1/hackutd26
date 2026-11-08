# OPS engineering handoff (#47)

## What exists

- `apps/ops/chaos_harness/` — 8 adversarial scenarios vs injectable
  backends → PASS/FAIL/NOT_RUN; `write_artifacts()` JSON+MD reports.
- `apps/ops/demo/` — deterministic demo scripts (90s + 3min Winstead),
  timed transcript, rollback plan, submission checklist.
- `docs/10-TEST-AND-DEMO.md` — authoritative test/demo plan.

## Integration touchpoints

- Chaos harness consumes the same backends as #53 acceptance runner —
  run both against live deployment for W01–W05 evidence.
- Demo transcript artifacts feed #38 submission package.
- Rollback plan references #34/#35 executor revert + audit recovery.

## Known limitations / risks

- **No live demos possible** — transcripts are scripted SIMULATED;
  the 3 uninterrupted live demos + screen recordings require the
  deployed stack on stage.
- Chaos scenarios use in-memory doubles — real evidence needs live
  endpoints (`--mode live_endpoint` path reserved).
- Release freeze (#55) not yet executed — no tagged release exists.

## Next steps

1. Deploy stack; run chaos harness + acceptance runner live; commit
   artifacts.
2. Execute 3 uninterrupted demos; record screen + transcripts.
3. Run 90-second tri-track rehearsal (#54) on-site.
4. Tag release; freeze per #55; assemble judge package.
