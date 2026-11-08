# Phantom Command — agent handoff

This is a UI development foundation in `apps/dashboard/twin`, extending the existing Sentinel twin React/Vite project. The entry screen is a technical integration gallery. The full command center and real backend workflows are intentionally left for the next implementation phase.

## Start here

From the repository root:

```sh
cd apps/dashboard/twin
npm ci
npm run dev
```

Open the local URL printed by Vite. No environment variables, API keys, inference service, database, or networked rover are needed. Use Node 22.13 LTS, 24 LTS, or 26+ (Node 26.12.1 and npm 11.20.0 were used for validation). See `VALIDATION.md` for executed checks and limitations.

The existing `src/main.jsx`, `src/Twin.jsx`, and `src/demoFeed.js` remain intact. Their original standalone demo is available at `/legacy.html` in both dev and production builds. Its older moving demo feed is simulated; it is separate from the deterministic new examples.

## Exact installed direct dependencies

All versions are pinned and `package-lock.json` is committed as a deliverable. Full transitive metadata is in `DEPENDENCY_INVENTORY.json`; package licenses and official repository URLs are in `THIRD_PARTY_LICENSES.md`. Regenerate those with `npm run licenses` after dependency changes.

| Package | Version | Use |
|---|---|---|
| `@ag-ui/client` | `1.0.2` | Runtime |
| `@ag-ui/core` | `1.0.2` | Runtime |
| `@copilotkit/react-core` | `1.85.0` | Runtime |
| `@copilotkit/react-ui` | `1.85.0` | Runtime |
| `@fontsource-variable/geist` | `5.3.0` | Runtime |
| `@hookform/resolvers` | `7.0.3` | Runtime |
| `@radix-ui/react-label` | `2.1.17` | Runtime |
| `@radix-ui/react-slot` | `1.5.0` | Runtime |
| `@react-three/drei` | `9.122.0` | Runtime |
| `@react-three/fiber` | `8.18.0` | Runtime |
| `@react-three/postprocessing` | `2.19.1` | Runtime |
| `@xyflow/react` | `12.12.1` | Runtime |
| `ag-grid-community` | `36.3.0` | Runtime |
| `ag-grid-react` | `36.3.0` | Runtime |
| `class-variance-authority` | `0.7.1` | Runtime |
| `cmdk` | `1.1.1` | Runtime |
| `cn` | `0.5.2` | Runtime |
| `echarts` | `6.1.0` | Runtime |
| `lucide-react` | `1.70.0` | Runtime |
| `next-themes` | `0.4.6` | Runtime |
| `postprocessing` | `6.39.6` | Runtime |
| `radix-ui` | `1.8.1` | Runtime |
| `react` | `18.3.1` | Runtime |
| `react-dom` | `18.3.1` | Runtime |
| `react-grid-layout` | `2.3.0` | Runtime |
| `react-hook-form` | `7.91.0` | Runtime |
| `react-resizable-panels` | `4.19.1` | Runtime |
| `rxjs` | `7.8.1` | Runtime |
| `sonner` | `2.0.8` | Runtime |
| `three` | `0.187.0` | Runtime |
| `tw-animate-css` | `1.4.0` | Runtime |
| `vaul` | `1.1.2` | Runtime |
| `zod` | `4.6.7` | Runtime |
| `zustand` | `5.1.0` | Runtime |
| `@eslint/js` | `10.0.1` | Development |
| `@playwright/test` | `1.65.0` | Development |
| `@tailwindcss/vite` | `4.3.5` | Development |
| `@types/node` | `26.6.6` | Development |
| `@types/react` | `18.3.31` | Development |
| `@types/react-dom` | `18.3.7` | Development |
| `@types/three` | `0.187.0` | Development |
| `@vitejs/plugin-react` | `6.2.1` | Development |
| `eslint` | `10.14.0` | Development |
| `eslint-plugin-react-hooks` | `7.1.1` | Development |
| `globals` | `17.14.0` | Development |
| `shadcn` | `4.23.0` | Development |
| `tailwindcss` | `4.3.5` | Development |
| `typescript` | `6.0.3` | Development |
| `typescript-eslint` | `8.72.1` | Development |
| `vite` | `8.3.6` | Development |
| `vitest` | `5.1.0` | Development |

## Compatibility decisions

- Preserve the existing React 18.3.1 runtime. The official [Fiber installation guide](https://r3f.docs.pmnd.rs/getting-started/installation) pairs React 18 with Fiber 8. Fiber 9 and Drei 10 require a coordinated React 19 migration. This foundation uses the last stable compatible Fiber 8, Drei 9 and React postprocessing 2 releases.
- Three 0.187.0 is within postprocessing 6.39.6's declared `>=0.168 <0.188` peer range. Three's TypeScript declarations are supplied by `@types/three` at the same revision. Application TS is strict; third-party declaration checking is skipped with `skipLibCheck`.
- TypeScript 6.0.3 is within typescript-eslint 8.72.1's `>=4.8.4 <6.1` peer range. TypeScript 7 is deliberately excluded. Vite 8 and its matching React plugin retain the existing Vite architecture and add Tailwind's Vite plugin and two HTML entry points.
- AG Grid React and Community use exactly the same version. Only `AllCommunityModule` is registered. Its current theme API injects its own styles; legacy AG Grid CSS must not also be imported.
- React Grid Layout 2 has bundled types and the `gridConfig`, `dragConfig`, and `resizeConfig` API. Do not follow v1 examples using `cols` directly on `GridLayout`. A documented ref type assertion in the example bridges its React 19 style declaration to React 18; no runtime coercion occurs.
- CopilotKit core/UI match at 1.85.0. The local AG-UI transport uses 1.0.2 to match the SDK's protocol dependency. It does not use any paid cloud service. CopilotKit's explicit development transport is for examples only.
- shadcn was acquired with its official CLI. Most components use Radix Nova; `form.tsx` comes from the official New York registry because the current Nova registry no longer generates that React Hook Form wrapper. Both are editable local MIT source.

## Project layout

```text
src/
  App.tsx, main.tsx           gallery shell and new TypeScript entry
  main.jsx, Twin.jsx         preserved legacy entry/scene
  components/
    ui/                      editable shadcn primitives
    phantom/                 shared custom example error boundary
  features/
    digital-twin/            future application feature boundaries
    cybersecurity/
    incidents/
    rover/
    intelligence/
  lib/
    three/                   map coordinates and R3F primitives
    charts/                  typed ECharts options
    graphs/                  React Flow fixture graph
    tables/                  typed AG Grid columns
    agents/                  provider boundary and local AG-UI transport
  styles/                    tokens.css, palette.ts, index.css, lab.css
  store/                     use-phantom-store.ts
  types/                     agent and security contracts
  mock/                      fixed evidence, devices and telemetry
  examples/                  seven independent integration screens
  hooks/                     shadcn responsive hook
public/THIRD_PARTY_NOTICES.txt complete shipped license/NOTICE texts
scripts/generate-licenses.mjs reproducible inventory and notices
```

## Component inventory and imports

Local shadcn components include Button, Card, Dialog, Sheet, Drawer, Table, Badge, Form, Input, InputGroup, Label, Select, DropdownMenu, Tooltip, Tabs, Sidebar, ScrollArea, ResizablePanelGroup/Panel/Handle, Alert, Sonner Toaster, Command, Progress, Slider, Switch, Separator, Skeleton, Textarea and Checkbox.

```tsx
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { usePhantomStore } from '@/store/use-phantom-store'

const selected = usePhantomStore(state => state.selectedDeviceId)
const selectDevice = usePhantomStore(state => state.selectDevice)
```

`@` maps to `src` in Vite and TypeScript. Import component files directly. The root shell wraps examples in `TooltipProvider`, `SidebarProvider`, and `AgentBoundary`, with a dark Sonner toaster. React Hook Form supports `Form` and `FormField`; `ComponentGallery.tsx` demonstrates required-field validation. The Sidebar example includes a mobile sheet and keyboard trigger.

| Library | Import / location | Integration details |
|---|---|---|
| Tailwind | `src/styles/index.css`, `@tailwindcss/vite` | v4 CSS imports; no v3 PostCSS setup |
| Lucide | `import { Shield } from 'lucide-react'` | Named vector components |
| Fiber / Three | `Canvas` from `@react-three/fiber`; math/objects from `three` | `DigitalTwinExample.tsx` |
| Drei | `OrbitControls`, `Line` from `@react-three/drei` | Controls and patrol line in `lib/three/primitives.tsx` |
| Postprocessing | `Bloom`, `EffectComposer` from `@react-three/postprocessing` | Composer belongs inside Canvas; switch toggles it |
| AG Grid | `AgGridReact` from `ag-grid-react` | Register Community modules; provide a theme object and a sized container |
| React Flow | `ReactFlow` from `@xyflow/react` | Import `@xyflow/react/dist/style.css`; use sized container, nodes and edges |
| ECharts | `init`, `use` from `echarts/core` | Register LineChart, Grid/Tooltip/Aria components and CanvasRenderer; observe resize and dispose on unmount |
| React Grid Layout | `GridLayout`, `useContainerWidth` from `react-grid-layout` | Import its styles plus `react-resizable/css/styles.css`; `LayoutExample.tsx` |
| Zustand | `create` from `zustand` | Select individual values/actions from `usePhantomStore` |
| CopilotKit | `CopilotKit`, `useCopilotReadable`, `useCopilotAction` from `@copilotkit/react-core`; `CopilotChat` from `@copilotkit/react-ui` | Lazy optional local conversation; import `@copilotkit/react-ui/styles.css` |

## Design tokens

Edit `src/styles/tokens.css` for CSS/shadcn tokens and `src/styles/palette.ts` for the corresponding Three/ECharts/React Flow values. Keep the nine named colors synchronized. All values match the supplied Phantom palette. `lab.css` styles only the technical gallery. Semantic shadcn variables map to the Phantom colors, including primary, panel, border and sidebar tokens. Geist is installed and bundled locally under OFL-1.1; technical labels use the system monospace stack. No remote font request is made.

## Spatial primitives and coordinate convention

The map frame is right-handed: map +x is world +X, map +y is world −Z, world +Y is height. Default units are meters. There is no sensor calibration or SLAM inference.

```tsx
import { mapToWorld, wallFromEndpoints } from '@/lib/three/coordinates'
import { WireframeWall, ServerRack, RoverMarker, SelectableObject } from '@/lib/three/primitives'

const frame = { origin: { x: 100, y: 200 }, metersPerUnit: 0.05 }
const position = mapToWorld({ x: 120, y: 240 }, 0.3, frame) // [1, 0.3, -2]
// In Canvas:
<WireframeWall start={{ x: -5, y: -4 }} end={{ x: 5, y: -4 }} height={2} />
<SelectableObject id="rack-01" onSelect={selectDevice}>
  <ServerRack at={{ x: -2, y: 2 }} selected={selected === 'rack-01'} />
</SelectableObject>
```

Available primitives: WireframeWall, FloorGrid, ServerRack, RoverMarker, SecurityZone, ThreatMarker, PatrolPath, SelectableObject, CameraControls. Walls derive center, length and yaw from endpoints. Height, wall thickness, rack dimensions and zone width/depth are world meters; `metersPerUnit` applies to map positions and endpoint lengths. Heading is radians counterclockwise from map +x; the rover nose points local +X. `CameraControls` supports orbit/pan/zoom plus an explicit reset key. Geometry rejects degenerate walls and nonfinite coordinates. Object selection also has table/select alternatives.

The new spatial example uses a fixed authored layout and fixed rover pose. Its path is illustrative. A future adapter must attach observation timestamps, source, measured confidence, calibration and stale status separately from visualization dimensions; never present authored geometry as reconstructed measurements. The legacy scene uses its historical coordinate convention and must be migrated explicitly before sharing real poses.

## Mock Nemotron provider

`src/types/agent.ts` defines AgentProvider, AgentContext, AgentTask, AgentEvent, AgentAction, AgentStatus, AgentFinding and ActionApproval. These cover investigation lifecycle, structured actions, evidence references, uncertainty, shared context, provenance and human approval decisions. `AgentBoundary` is the React injection boundary; `AgentContext` is incident context data, not a React context object.

```tsx
import { MockAgentProvider } from '@/lib/agents/mock-provider'
import { AgentBoundary, useAgentProvider } from '@/lib/agents/context'
import { agentContext } from '@/mock/security'

const provider = new MockAgentProvider()
const stop = provider.subscribe(event => console.log(event))
await provider.investigate({ id: 'unique-task-id', title: 'Inspect fixture', context: agentContext })
// Emits investigating → finding → pending approval → awaiting_approval.
await provider.decide('approval-unique-task-id', 'approved', 'demo-operator', 'Reviewed fixture')
stop()
provider.dispose()
```

The provider accepts only SYNTHETIC context. Events use a fixed UTC epoch plus deterministic sequence offsets, and investigations accept AbortSignal. Each task ID must be unique. Approval is explicit; rejection emits no action; repeat decisions and self-approval are rejected. Approved events say `simulated` and never call an actuator. Store subscriptions deduplicate event IDs. The root provider remains mounted across examples, allowing background events and shared context without opening chat. The mock status stream intentionally advances on a microtask rather than a random timer.

The optional CopilotKit example registers readable shared context and an allowlisted fixture selection tool. `CopilotMockAgent` is a local AG-UI AbstractAgent that emits a fixed text response. It does not choose tools or perform reasoning. The app passes it via `agents__unsafe_dev_only` with no runtime URL, cloud key, inspector or paid features. This option must be removed for production integration. The mock agent/proposal flow and the optional conversation are separate examples of the same provider boundary, not a claim of a Nemotron connection.

## Mock data conventions

- New fixture data is static or deterministic, with a fixed timestamp of `2026-11-07T18:00:00.000Z` and explicit SYNTHETIC provenance.
- Device IDs are stable across the table, graph, 3D scene, and shared store. IP addresses use 192.0.2.0/24 documentation space.
- All referenced evidence IDs are fixtures; no camera photos, sensor-derived positions or real compromise are asserted. Radio anomalies never establish exfiltration.
- Use explicit unknown/unverified states and retain evidence links and uncertainty when extending contracts. Keep raw observations separate from visual interpolation and authored map assumptions.
- Graph and grid layout edits are local to their mounted example. Selection, bloom, agent findings and approvals use Zustand. Nothing is persisted across reloads.

## Recommended application architecture / next steps

1. Read `docs/06-WINSTEAD-COMPLIANCE.md`, `docs/07-COMMAND-CENTER.md` and `docs/04-DATA-AND-INTERFACES.md` in the repository root. This gallery is not evidence of W01–W05 compliance.
2. Compose product screens under `src/features/*` using these primitives. Build incident queue/documentation, scope matrix, team communication and approved response workflows as separate authorized features. Keep the conversational interface secondary.
3. Add authenticated, server-authorized SpacetimeDB projections or a gateway adapter for device, incident, rover and evidence streams. Preserve LIVE/REPLAY/SYNTHETIC and stale timestamps. Do not put credentials or raw unrestricted evidence in browser subscriptions.
4. Implement AgentProvider on the backend adapter. Parse and schema-validate incoming AgentEvents, bound event history, support reconnect/deduplication, and attach server-assigned identity and evidence. Current mock types are frontend contracts, not a deployed backend API change.
5. Replace the optional CopilotKit development transport with an authenticated same-origin runtime connected to a Nemotron backend. Register small allowlisted UI tools. No browser tool may directly perform containment, scanning, or rover navigation.
6. All approval identity, permission checks, reason validation, separation of duties, authorization and execution must be enforced server-side. Local guards demonstrate UX only. Track proposed, approved, dispatched and verified outcomes separately when the actual backend exists.
7. Add schema versioning and conflict handling before connecting real incident edits. Keep observability and error/disconnected states explicit. Add real service integration tests before any operational or sponsor-compliance claim.

## Limits and maintenance

WebGL2 is required for 3D; an error boundary provides a visible fallback. No GLB/texture/model downloads or SLAM system are included. No live identity, incident chat, network discovery, rover navigation, Nemotron inference or containment is implemented. The legacy feed is preserved but not claimed as a production telemetry integration.

Examples are lazy-loaded because AG Grid, Three, ECharts and CopilotKit are large. CopilotKit's stock Markdown renderer also brings syntax highlighters and diagram chunks; production bundle size remains a follow-up. Audit findings are documented in `VALIDATION.md`; install/build success does not mean dependencies are free of advisories.

Retain `public/THIRD_PARTY_NOTICES.txt` with distributions. Re-run `npm run licenses` after `npm ci` when dependencies change, preserving upstream source/NOTICE files. Upgrade React/Fiber/Drei/postprocessing together rather than independently. Run the validation commands from the README before handing off further changes.
