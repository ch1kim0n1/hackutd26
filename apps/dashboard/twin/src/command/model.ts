export type Point = { x: number; y: number }
export const WORKSPACES = ['overview', 'twin', 'network', 'incidents', 'rover', 'intelligence'] as const
export type Workspace = typeof WORKSPACES[number]
export type CameraMode = 'isometric' | 'top' | 'orbit' | 'follow'
export type ScenarioId = 'patrol' | 'unknown' | 'impersonation' | 'tamper' | 'correlated' | 'resolution'
export type ObservationKind = 'unknown' | 'impersonation' | 'tamper' | 'correlated'
export type Severity = 'low' | 'medium' | 'high' | 'critical'
export type DeviceKind = 'server' | 'ap' | 'sensor' | 'rover' | 'wifi' | 'ble'
export interface Zone { id: string; name: string; code: string; bounds: [number, number, number, number]; position: Point; color: string }
export interface Device { id: string; name: string; kind: DeviceKind; zoneId: string; position: Point; status: 'healthy' | 'watch' | 'threat'; statusKnown?: boolean; protocol: 'Ethernet' | 'Wi-Fi' | 'BLE' | 'System'; address: string; vendor: string; risk: number; rssi: number; lastSeen: number; signalHistory: number[] }
export interface Observation { id: string; kind: ObservationKind; zoneId: string; deviceIds: string[]; at: number; detail: string; observedAtUtc?: string }
export interface TimelineEntry { id: string; at: number; title: string; detail: string; kind: 'observation' | 'analysis' | 'mission' | 'evidence' | 'resolution' | 'operator' }
export interface Incident { id: string; title: string; severity: Severity; status: 'detected' | 'investigating' | 'collecting' | 'resolved'; zoneId: string; deviceIds: string[]; observationIds: string[]; evidenceIds: string[]; findingIds: string[]; timeline: TimelineEntry[]; createdAt: number; updatedAt: number }
export interface Evidence { id: string; incidentId: string; type: 'rf' | 'camera' | 'lidar' | 'policy'; at: number; summary: string }
export interface Finding { id: string; incidentId: string; at: number; title: string; detail: string; confidence: number; evidenceIds: string[] }
export interface AgentRecord { id: string; at: number; kind: 'observation' | 'correlation' | 'tool' | 'decision' | 'finding' | 'status'; title: string; detail: string; incidentId?: string; tool?: string; outcome?: string }
export interface Mission { id: string; title: string; type: 'patrol' | 'investigate' | 'waypoint' | 'return'; status: 'queued' | 'en_route' | 'collecting' | 'complete' | 'cancelled'; target: Point; zoneId?: string; incidentId?: string; progress: number; route?: Point[]; routeIndex?: number; routeLength?: number; travelled?: number; collectingAt?: number; collectionElapsed?: number }
export interface Approval { id: string; at: number; incidentId: string; action: 'isolate-device'; targetId: string; reason: string; status: 'pending' | 'approved' | 'rejected'; decidedAt?: number }
export interface Rover { position: Point; heading: number; speed: number; battery: number; stopped: boolean; missionId: string | null; distance: number; lidar: number[]; stale?: boolean; frameId?: string; poseAt?: number; provenance?: string }
export type TwinProvenance = 'LIVE' | 'REPLAY' | 'DEMO'
/** Latest occupancy-grid snapshot for one frame_id, normalized to
 * canonical cells (-1 unknown | 0 free | 100 occupied). origin is
 * facility-frame (registration already applied). Heights rendered from
 * this map are INFERRED — never LiDAR/surveyed measurements. */
export interface TwinOccupancyMap {
  frameId: string; revision: number; resolutionM: number
  origin: Point; width: number; height: number
  timestampMicros: number; provenance: TwinProvenance
  registered: boolean; registration: 'identity' | 'static-offset' | 'unregistered'
  cells: Int8Array
  unknown: number; free: number; occupied: number
  stale: boolean; ageSeconds: number
}
/** Registered (surveyed) position of an edge device — pucks/Pi-class
 * units — expressed in facility coordinates. */
export interface TwinAnchor { id: string; x: number; y: number; label?: string; frameId: string }
export interface TwinFeedState { maps: TwinOccupancyMap[]; anchors: TwinAnchor[] }
export const EMPTY_TWIN_FEED: TwinFeedState = { maps: [], anchors: [] }
export interface TelemetrySample { at: number; traffic: number; signals: number; cpu: number; latency: number }
export interface CommandEvent { id: string; at: number; type: string; entityId?: string; detail: string }
export interface CommandState {
  elapsed: number; speed: number; simulation: 'ready' | 'running' | 'paused'; scenario: ScenarioId;
  zones: Zone[]; devices: Device[]; observations: Observation[]; incidents: Incident[]; evidence: Evidence[];
  findings: Finding[]; activity: AgentRecord[]; missions: Mission[]; approvals: Approval[]; events: CommandEvent[];
  rover: Rover; telemetry: TelemetrySample[]; twinFeed: TwinFeedState; sequence: number; scenarioStep: number; tickRemainder?: number;
}
export type CommandMode = 'demo' | 'live'
export type LivePhase = 'off' | 'connecting' | 'online' | 'degraded' | 'error'
export interface CommandStore {
  state: CommandState; workspace: Workspace; selectedId: string | null; camera: CameraMode;
  mode: CommandMode; livePhase: LivePhase; liveDetail: string;
  setMode: (mode: CommandMode) => void; applyLive: (snapshot: import('./live/types').LiveSnapshot) => void;
  navigate: (workspace: Workspace) => void; select: (id: string | null) => void; setCamera: (camera: CameraMode) => void;
  start: () => void; pause: () => void; reset: (scenario?: ScenarioId) => void; setSpeed: (speed: number) => void; setScenario: (scenario: ScenarioId) => void;
  tick: (seconds: number) => void; inject: (kind: ObservationKind) => void;
  emergencyStop: () => void; releaseStop: () => void; returnHome: () => void; waypoint: (target: Point, zoneId?: string) => void;
  decideApproval: (id: string, approve: boolean) => void; createIncident: (title: string, zoneId: string, severity: Severity) => void;
  retryInspection: (incidentId: string) => void;
}
export const SCENARIOS: { id: ScenarioId; name: string; description: string }[] = [
  { id: 'patrol', name: 'Normal patrol', description: 'Routine perimeter monitoring and a clean wireless baseline.' },
  { id: 'unknown', name: 'Unknown transmitter', description: 'An unregistered BLE transmitter appears in the server hall.' },
  { id: 'impersonation', name: 'AP impersonation', description: 'A duplicate SSID with a mismatched fingerprint triggers investigation.' },
  { id: 'tamper', name: 'Physical tampering', description: 'A cabinet sensor change prompts visual inspection.' },
  { id: 'correlated', name: 'Correlated anomalies', description: 'Wireless and physical observations link to the same location.' },
  { id: 'resolution', name: 'Autonomous resolution', description: 'Follow the complete sense → investigate → report workflow.' },
]
export const BASE_TIME = Date.parse('2026-11-07T18:42:00.000Z')
export function formatTime(seconds: number) { return new Date(BASE_TIME + seconds * 1000).toISOString().slice(11, 19) }
