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

## Dependency audit — unresolved

`npm audit --json` reported **34 affected-package entries: 13 high, 13 moderate and 8 low**, with no critical entries. `npm audit --omit=dev --json` reported **19 entries: 13 high and 6 low**. These are propagated package counts, not 34 distinct advisories. The four root advisories are:

| Package | Advisory | Scope |
|---|---|---|
| zod `<4.6.6` | [Oversized constrained collections can exhaust memory](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5) | CopilotKit / AG-UI transitive Zod 3 dependencies; the application's direct Zod 4.6.7 is outside the reported range |
| katex `<0.18.2` | [Prototype pollution can bypass trust restrictions](https://github.com/advisories/GHSA-238p-pmpm-9mq7) | CopilotKit's Markdown/diagram renderer dependencies |
| minimatch `>=7 <11.0.1` | [Globparts amplification denial of service](https://github.com/advisories/GHSA-g3hv-75wg-m249) | Development tooling |
| deepmerge `>=4.2.0 <=4.3.1` | [Prototype poisoning of returned objects](https://github.com/advisories/GHSA-gcqx-w48m-w2h4) | shadcn development CLI / registry |

The requested stable SDKs install and run together, but their dependency trees are not audit-clean. No forced Zod major-version override or `npm audit fix --force` was applied: those would change upstream API contracts and the verified compatibility set. This foundation uses fixed local fixtures and an in-memory transport. Resolve or re-evaluate these advisories with compatible upstream patches before accepting untrusted agent events, model output or backend data. Re-run both audit commands when dependencies change; do not interpret the successful build as a security review.

## Remaining integration and distribution limits

All observations, camera/LiDAR displays, agent assessments, rover movement and containment records are synthetic. ROS 2, Kismet, Nemotron inference, production authentication/authorization and physical E-stop/watchdog hardware are typed future integration boundaries, not connected implementations. Browser approvals only authorize a local simulation record. No sponsor-compliance or live-service acceptance claim is made.

Vite reports large lazy chunks for Three, AG Grid and CopilotKit. CopilotKit's optional Markdown renderer includes many syntax/diagram modules; bundle reduction remains future work. Its in-memory `agents__unsafe_dev_only` transport must be replaced by an authenticated runtime for a live deployment. GSAP is distributed under its standard no-charge license, retained in the generated notice bundle.

State and layout edits are local to the session/view and are not a durable incident database. No external deployment was performed by this implementation task.
