# Issue Execution Board — SENTINEL HIVE

This is the **canonical work breakdown** for the GitHub issue tracker. All issues are unassigned at creation. Each epic has three implementation tickets and one FINALIZE acceptance gate; cross-team GLUE issues exercise actual working integration.

## Tracker

| Epic | Implementation | Finalization | Integration dependencies |
|---|---|---|---|
| [HW #1](https://github.com/ch1kim0n1/hackutd26/issues/1) Rover + motor safety | #10 #11 #12 | #39 | #48 #50 #54 |
| [RF #2](https://github.com/ch1kim0n1/hackutd26/issues/2) Pucks and RF | #13 #14 #15 | #40 | #48 #49 #51 #54 |
| [DATA #3](https://github.com/ch1kim0n1/hackutd26/issues/3) SpacetimeDB + gateway | #16 #17 #18 | #41 | #48 #49 #50 #51 #52 #54 |
| [AI #4](https://github.com/ch1kim0n1/hackutd26/issues/4) Nemotron | #19 #20 #21 | #42 | #49 #50 #54 |
| [SEC #5](https://github.com/ch1kim0n1/hackutd26/issues/5) Winstead isolation and RBAC | #22 #23 #24 | #43 | #52 #53 #54 |
| [IR #6](https://github.com/ch1kim0n1/hackutd26/issues/6) Winstead docs/scope/chat | #25 #26 #27 | #44 | #51 #52 #53 #54 |
| [UX #7](https://github.com/ch1kim0n1/hackutd26/issues/7) Digital twin and radio UI | #28 #29 #32 | #45 | #51 #53 #54 |
| [ACT #8](https://github.com/ch1kim0n1/hackutd26/issues/8) Containment | #33 #34 #35 | #46 | #52 #53 #54 |
| [OPS #9](https://github.com/ch1kim0n1/hackutd26/issues/9) Build/deployment/tests | #36 #37 #38 | #47 | #53 #54 #55 |

## Cross-team glue chain

1. [#48 Device-to-SpacetimeDB](https://github.com/ch1kim0n1/hackutd26/issues/48) — HW + RF + DATA
2. [#49 Incident-to-Nemotron](https://github.com/ch1kim0n1/hackutd26/issues/49) — RF + DATA + AI
3. [#50 Nemotron-to-rover](https://github.com/ch1kim0n1/hackutd26/issues/50) — HW + DATA + AI
4. [#51 Twin/RF/evidence-to-incident UI](https://github.com/ch1kim0n1/hackutd26/issues/51) — RF + DATA + IR + UX
5. [#52 Approval-to-verified-containment](https://github.com/ch1kim0n1/hackutd26/issues/52) — DATA + SEC + IR + ACT
6. [#53 Winstead hostile-network requirements](https://github.com/ch1kim0n1/hackutd26/issues/53) — SEC + IR + UX + ACT; W01–W05 all PASS
7. [#54 Integrated physical tri-track rehearsal](https://github.com/ch1kim0n1/hackutd26/issues/54) — full system three repeated runs
8. [#55 Final deployment and judge-ready release](https://github.com/ch1kim0n1/hackutd26/issues/55) — requires #48–#54 plus #39–#47 and no release-blocking failures

## Recommended parallel execution

**Day zero:** Freeze actual BOM and architecture, independently secure management host, pin model/SDK versions (#10, #16, #19, #22, #36).

**Wave 1 (parallel):** Firmware (#11,#12), sensor nodes (#13,#14), state engine (#16,#17), agent tools (#19,#20), identity (#22,#23), incident core (#25–#27), UI scaffolding (#28–#29), containment policies (#33–#34).

**Wave 2:** Glue #48–#52 when the interfaces exist; repair contract mismatches in originating implementation issue, not by hardcoding one-off demonstration adapters.

**Wave 3:** Run subsystem finalization #39–#47, Winstead adversarial signoff #53, repeated end-to-end #54, then final release #55. Some signoff tests may run earlier; nothing is marked complete before proof.

## GitHub issue etiquette

- Names use `[EPIC]`, `[HW/RF/DATA/AI/SEC/IR/UX/ACT/OPS]`, `[FINALIZE]` or `[GLUE-XX]`.
- Assign an owner to each implementation and finalization issue. Keep issues open while tests or Winstead checks fail.
- PR description includes "Closes #issue-number" only when the acceptance gate will really pass; otherwise "Refs #issue-number".
- Changes to event schemas require update to docs/04; changes to authorization/incident UX require review against docs/06.
- Track actual reproduced test artifact or signed-off recording in issue comments and docs/tests evidence.
- A mock UI, synthetic RF waterfall or unverified containment **does not satisfy** a live acceptance gate.

## Note on duplicate issues

#30 and #31 were inadvertently created during issue batching, then marked closed as duplicates of canonical #28 and #29 respectively. Use #28 and #29.

**Final release hard blockers:** an independent command center under fully compromised internal office network; all five Winstead requirements proven, real Nemotron tool use, real SpacetimeDB primary state, safe autonomous rover, explicit authorization and independently verified lab containment.
