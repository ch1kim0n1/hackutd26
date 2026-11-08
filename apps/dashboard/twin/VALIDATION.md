# Phantom Command validation — 7 November 2026

Validated on macOS arm64 with Node 26.12.1, npm 11.20.0 and Playwright Chromium 158.0.8127.18. This record covers the complete deterministic frontend and the retained component laboratory.

Integration with upstream `main` at `400cf04` preserves its robotics changes and carries the warm slate/gold legacy styling into `/legacy.html`. After resolving the entry-page conflict, lint, all 23 unit tests, strict TypeScript and the production build passed again. Both targeted browser checks (all six command workspaces and the preserved legacy entry) passed in 12.3 seconds.

| Check | Result |
|---|---|
| Dependency installation | Exact Motion 14.10.1 and GSAP 3.15.1 added to the existing compatible React 18 stack; lockfile synchronized |
| Dependency tree | `npm ls --all --json` exited 0 with no dependency-tree problems |
| Strict TypeScript, ESLint, production build | `npm run check` passed; three entry pages emitted: main application, `/lab.html`, `/legacy.html` |
| Unit tests | 5 files, 23 tests passed |
| Browser integration | All 9 browser tests passed in one full production-build run (56.5 seconds) |
| License inventory | 53 exact direct dependencies and 1,126 installed entries; shipped license/NOTICE text retained |
| Occupancy geometry | 6,912 map cells, 407 occupied cells, 11 merged wall prisms; exact occupied area and open doorways verified |
| Patch whitespace | Source changes pass `git diff --cached --check` excluding `public/THIRD_PARTY_NOTICES.txt`, which retains upstream license text and its original whitespace |

Unit tests verify all six scenario replays, fixed-step/speed invariance, the full automatic investigation chain, immutable transitions, linked evidence, pause/resume, independent E-stop, geofencing and route clearance, operator approvals and duplicate decisions, rejected containment, interrupted mission reassignment, manual injection, context selection before/after observations, event subscriptions, future inference validation, local context briefs and occupancy conversion. The preserved provider/coordinate unit tests also pass. Added regressions prove that E-stop does not consume active evidence-capture time or publish early evidence, and that operator incident creation immediately updates agent context while the clock is idle; invalid creation preserves the prior selection.

The product browser checks cover all six workspaces, cross-view device and topology selection, filters, WebGL geometry, actual projected rack picking, top/follow cameras, RF layer controls, grid resizing, event injection, manual incident creation, waypoint dispatch, complete autonomous resolution, evidence/findings, pause/reset, E-stop/return-home/reassignment, human approval and the live-state CopilotKit context console. Navigation checks exercise initial deep links, in-panel links, browser Back/Forward with retained selection, reload, brand navigation, invalid hashes and restoration of isometric camera mode on return to overview. They also assert no horizontal overflow at 1024×768 and 390×844 with reduced motion enabled. The complete six-workspace check records browser errors and outgoing requests and requires zero errors and zero external HTTP requests.

Retained integration checks exercise all seven laboratory examples, including shadcn dialog/form controls, AG Grid, React Flow, ECharts, real grid resizing, 3D picking/orbit/bloom, approval contracts, local CopilotKit messages, mobile navigation and the preserved legacy demo.

Screenshots from the production build are saved in ignored `test-results/` and have been inspected for the overview, facility twin, network view, rover sensors, incident dossier, intelligence workspace, small desktop and mobile layout. Visual fixes include initial camera centering, removal of overlapping inspectors, consistent typography and explicit incident filter styling. In-app interactive inspection was blocked by that browser's URL policy; the repository's isolated automated Chromium regression workflow supplied the UI evidence.

Performance review: procedural geometry needs no remote assets; the 407 occupied cells become 11 wall prisms. DPR is capped at 1.5; bloom uses no multisampling; one spatial canvas is mounted per workspace. Component libraries and the optional CopilotKit console load on demand. WebGL tests use Chromium's software renderer; real-device GPU frame rates and other browser engines have not been benchmarked. Reduced-motion checks cover CSS, Motion, GSAP and Three camera/scan behavior.

## Dependency audit — triaged (#128, 2026-11-08)

`npm audit --json` reported **34 affected-package entries: 13 high, 13 moderate and 8 low**, with no critical entries. `npm audit --omit=dev --json` reported **19 entries: 13 high and 6 low**. These are propagated package counts, not 34 distinct advisories. The four root advisories are:

| Package | Advisory | Triage (#128) |
|---|---|---|
| zod `<4.6.6` | [Oversized constrained collections can exhaust memory](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5) | **upstream-blocked → accepted-risk.** Only inside CopilotKit/AG-UI transitive Zod 3 trees; direct `zod@4.6.7` is outside the range. Latest `@copilotkit/react-core@1.85.0` still carries the vulnerable tree; the only audit-reported fix is a breaking CopilotKit contract change (non-goal). Accepted because the foundation consumes fixed local fixtures and in-memory transport only — no untrusted agent events, model output, or backend data are validated by these trees. |
| katex `<0.18.2` | [Prototype pollution can bypass trust restrictions](https://github.com/advisories/GHSA-238p-pmpm-9mq7) | **upstream-blocked → accepted-risk.** Transitive via CopilotKit markdown/diagram renderers (`@copilotkit/react-core@1.85.0` latest still affected). Same trust boundary as above: renderer never receives untrusted content in the foundation. |
| minimatch `>=7 <11.0.1` | [Globparts amplification denial of service](https://github.com/advisories/GHSA-g3hv-75wg-m249) | **upstream-blocked → accepted-risk.** Dev-only (eslint/typescript-eslint/ts-morph pin `^10`; installed 10.2.6). Fix requires minimatch 11.x which no parent range accepts; not shipped in the bundle. |
| deepmerge `>=4.2.0 <=4.3.1` | [Prototype poisoning of returned objects](https://github.com/advisories/GHSA-gcqx-w48m-w2h4) | **upstream-blocked → accepted-risk.** Dev-only via `shadcn@4.23.0` (latest) → `@shadcn/registry`; **no fixed release exists** (latest deepmerge is 4.3.1). Not shipped. |

**Safe-upgrade attempt (#128):** all direct dependencies are already at latest (`@copilotkit/react-core`/`react-ui` 1.85.0, `zod` 4.6.7, `shadcn` 4.23.0). `npm audit fix` (non-force) was run: it only deduplicated `react-dom`/`scheduler` in the lockfile (20 added lines) and changed **no** advisory counts — `npm audit --omit=dev` still reports 19 (13 high, 6 low). `npm audit fix --force` was NOT run: its only path is a breaking CopilotKit downgrade/contract change, explicitly out of scope.

**Re-verification (#128):** `npx vitest run` 56/56 pass; `npm run build` succeeds; pytest sweep all green (rover 160+3 skip, autonomy 18, api 18, nemotron_client 28, investigator 8, hardening 15, pucks 16, sdr 10, correlator 11, wand 7). `npm run check` fails at lint on **7 pre-existing unused-var errors on main** (unrelated to dependencies; filed as issue #136 — `src/`/`tests/` are outside this issue's ownership).

**Standing rule (unchanged):** do not interpret the successful build as a security review. Re-run `npm audit` and `npm audit --omit=dev` when dependencies change; resolve or re-evaluate these advisories with compatible upstream patches before accepting untrusted agent events, model output or backend data.

## Remaining integration and distribution limits

All observations, camera/LiDAR displays, agent assessments, rover movement and containment records are synthetic. ROS 2, Kismet, Nemotron inference, production authentication/authorization and physical E-stop/watchdog hardware are typed future integration boundaries, not connected implementations. Browser approvals only authorize a local simulation record. No sponsor-compliance or live-service acceptance claim is made.

Vite reports large lazy chunks for Three, AG Grid and CopilotKit. CopilotKit's optional Markdown renderer includes many syntax/diagram modules; bundle reduction remains future work. Its in-memory `agents__unsafe_dev_only` transport must be replaced by an authenticated runtime for a live deployment. GSAP is distributed under its standard no-charge license, retained in the generated notice bundle.

State and layout edits are local to the session/view and are not a durable incident database. No external deployment was performed by this implementation task.

## M5 final validation — 2026-11-11 (#118)

**Dependency audit (re-run):** `npm audit` = 34 entries (8 low, 13 moderate, 13 high); `--omit=dev` = 19 (6 low, 13 high). Counts unchanged from #128 triage — no new advisories, no compatible upstream fixes released. Accepted-risk rationale above stands; nothing shipped to untrusted input paths.

**Test sweep (this pass):** twin `npm run check` green — eslint 0 errors (post-#136), vitest 60/60, vite build OK. Python: regression 4, scenarios 3, policy_actions 8, quarantine 7, deception 7, traffic_path 6, honeypot_service 7, datacenter 25, posture 9, prevention 7, hardening 9, risk_priority 9. Fixed during sweep: three test files used `parents[3]` (repo root) for sibling `sys.path` inserts — corrected to `parents[2]` (`apps/`); suites now self-contained without external PYTHONPATH.

**Naming decision:** SENTINEL HIVE is the platform/backend (SpacetimeDB module, gateway, collectors). Phantom Command is the command-center UI (`apps/dashboard/twin`). Phantom Patrol is the robot/rover program (`robotics/`, `autonomy/`). Docs use SENTINEL HIVE for architecture, Phantom Command for UI surfaces, Phantom Patrol for the vehicle. No rename needed; mapping documented here.

**Reset/failure modes:** `apps/datacenter/scripts/reset.py` tears down compose; vpi `/admin/release` clears quarantine; executor `revert()` restores isolation; hardening proposals expire and fingerprint-replay is denied; gateway rejects replayed seq and bad HMAC. Verified in pytest suites above.

**Performance notes:** twin prod bundle main chunk ~1.86 MB (576 KB gzip) — Three/AG Grid/CopilotKit lazy chunks; DPR capped 1.5; 407-cell occupancy merged to 11 wall prisms. Scenario runner completes all three flows in ~1 s on laptop.

**Residual risk (honest):** CopilotKit/AG-UI transitive advisories remain upstream-blocked (see #128 table). Physical hardware paths (serial, monitor-mode, real switch) are code-complete but lab-untested — see #54/#55.
