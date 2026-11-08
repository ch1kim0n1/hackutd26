# Phantom Command — implementation handoff

The complete simulated command center is implemented in `apps/dashboard/twin` on `codex/full-ui-implementation`. Read [README.md](README.md) for the walkthrough, architecture, integration boundaries, and commands; [VALIDATION.md](VALIDATION.md) records executed checks.

## Application ownership

- `src/App.tsx` owns the six-workspace shell, clock driver, simulation controls, search, navigation and optional context drawer.
- `src/command/model.ts` defines the shared contracts. `store.ts` is the only product store; `engine.ts` owns pure simulation transitions.
- `src/command/navigation.ts` connects all store navigation to hash URLs and browser Back/Forward. The shell mounts and cleans up that connection; individual panels should call `navigate`, never write browser history themselves.
- `agents.ts` contains the structured mock agent, tool registry, policy checks, context store and future inference boundary. `adapters.ts` describes future ROS 2/Kismet/robotics integrations without connecting anything.
- `src/command/twin/*` owns occupancy conversion and cinematic rendering. `workspaces/*` and `components/*` consume the same store.
- `src/styles/command.css` owns the shell/overview/rover styling; `workspaces/security.css` owns security workspaces; `twin/twin.css` owns the spatial view. Central palette values are in `src/styles/tokens.css` and `palette.ts`.

The product dataset has 32 entities, 3 zones, 12 racks, 4 APs, 3 monitors and 1 rover. The epoch is 2026-11-07 18:42:00 UTC. Simulation has fixed 250 ms steps and retains fractional steps for deterministic replay. Speed scales the clock. No random values or external requests participate in the product engine.

E-stop is an independent latched rover state. Evidence capture advances using `Mission.collectionElapsed` only while the rover is released and the simulation is running; `collectingAt` retains the original start timestamp. Policy permits bounded inspection; disruptive isolation remains pending until a separate demo operator decision. Return-home cancels previous missions, preserves E-stop, and leaves interrupted investigations open; the operator can reassign them. Operator incident creation uses the shared selection action to update agent context immediately. The optional chat is read-only deterministic context and never starts an investigation.

## Preserved foundation

`/lab.html` is the original seven-example integration laboratory (`FoundationApp.tsx`, `src/examples/*`). Its separate store/provider are fixtures, not the product engine. `/legacy.html` remains the original JavaScript moving twin demo. [FOUNDATION_HANDOFF.md](FOUNDATION_HANDOFF.md) preserves the original library/API notes; references there to a future complete app are historical. Current dependencies and exact licenses are generated in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

## Continue safely

Run `npm run check`, then `npm run test:ui` after building. Tests cover the pure engine, occupancy geometry, agent contracts, the complete automatic scenario, operator approvals, safety controls, cross-workspace selection, layouts, optional CopilotKit transport and preserved examples. Keep `public/THIRD_PARTY_NOTICES.txt` in builds.

Read-only ROS 2/Kismet adapters and future inference are typed boundaries, not live implementations. Real authentication, policy and robotics interlocks must be enforced by an independently secured backend before a live source is connected. The local approval UI is a simulation, not authorization for a real action. Keep evidence, observations, inference and presentation annotations distinct.
