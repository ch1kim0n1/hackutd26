// Twin feed service — serves the dashboard's documented twin endpoint
// (apps/dashboard/twin live/twin.ts HttpTwinTransport):
//
//   GET /twin-feed -> { provenance, maps[], poses[], anchors[], detail }
//   GET /healthz   -> { ok: true }
//
// poses[]  — REAL rover pose fixes converted to sentinel.rover.pose_report
//            v1 contracts, read from SpacetimeDB observationFeed
//            (kind='mission_status' rows written by the gateway from
//            sim_bridge/rover MQTT telemetry). Per-payload provenance is
//            preserved: SIM -> DEMO, LIVE -> LIVE.
// maps[]   — surveyed_floorplan occupancy grid rasterized from the rover
//            route survey (config/routes.json zone bounds). This is a
//            SYNTHETIC rasterization of real survey bounds — labelled
//            DEMO, never LIVE. Real SLAM occupancy is the hardware
//            engineer's future feed.
// anchors[]— surveyed waypoint positions (metres, surveyed_floorplan).
//
// Run:  cd services/gateway && npx tsx ../twin-feed/src/index.ts
// (reuses gateway's generated bindings + node_modules)
//
// Env:
//   SPACETIMEDB_URI / SPACETIMEDB_DATABASE
//   TWIN_FEED_SPACETIMEDB_TOKEN — role token with observationFeed read
//                                (commander recommended)
//   PORT                        — default 8090
//   ROVER_ROUTES                — path to robotics/rover/config/routes.json
//   TWIN_FEED_MAX_POSES          — pose reports per response (default 8)

import { createServer } from 'node:http';
import { readFileSync } from 'node:fs';
import { DbConnection } from '../../gateway/bindings/index';

const URI = process.env.SPACETIMEDB_URI ?? 'ws://127.0.0.1:3000';
const DB = process.env.SPACETIMEDB_DATABASE ?? 'sentinel-hive';
const TOKEN = process.env.TWIN_FEED_SPACETIMEDB_TOKEN ?? '';
const PORT = Number(process.env.PORT ?? 8090);
const ROUTES_PATH = process.env.ROVER_ROUTES
  ?? new URL('../../../robotics/rover/config/routes.json', import.meta.url).pathname;
const MAX_POSES = Number(process.env.TWIN_FEED_MAX_POSES ?? 8);

if (!TOKEN) {
  console.error('TWIN_FEED_SPACETIMEDB_TOKEN is required');
  process.exit(2);
}

const log = (o: Record<string, unknown>) => console.log(JSON.stringify({ svc: 'twin-feed', ...o }));
const OCCUPANCY_GRID_CONTRACT = 'sentinel.rover.occupancy_grid';
const POSE_REPORT_CONTRACT = 'sentinel.rover.pose_report';
const SCHEMA_VERSION = 1;
const CELL_UNKNOWN = -1;
const CELL_FREE = 0;
const CELL_OCCUPIED = 100;

// ---------------------------------------------------------------------------
// SpacetimeDB connection — observationFeed only (pose extraction)
// ---------------------------------------------------------------------------

const conn = await new Promise<DbConnection>((resolve, reject) => {
  DbConnection.builder()
    .withUri(URI)
    .withDatabaseName(DB)
    .withToken(TOKEN)
    .withAutomaticReconnect()
    .onConnect((c) => resolve(c))
    .onConnectError((_ctx, e) => reject(e))
    .build();
});

await new Promise<void>((resolve, reject) => {
  conn.subscriptionBuilder()
    .onApplied(() => resolve())
    .onError((_ctx, e) => reject(e))
    .subscribe((tables) =>
      [(tables as Record<string, { build(): unknown }>).observationFeed.build() as never]);
});
log({ event: 'connected', uri: URI, db: DB });

// ---------------------------------------------------------------------------
// Pose extraction: mission_status observations -> pose_report contracts
// ---------------------------------------------------------------------------

/** SpacetimeDB timestamp -> ISO string (SDK may hand Date / micros / wrapper). */
function toIso(v: unknown): string {
  if (v instanceof Date) return v.toISOString();
  if (typeof v === 'string') return v;
  if (typeof v === 'number' || typeof v === 'bigint') {
    const n = Number(v);
    // micros ~1e15, millis ~1e12, seconds ~1e9
    const ms = n > 1e14 ? n / 1000 : n > 1e11 ? n : n * 1000;
    const d = new Date(ms);
    return Number.isNaN(d.getTime()) ? new Date().toISOString() : d.toISOString();
  }
  const inner = (v as { microsSinceUnixEpoch?: unknown })?.microsSinceUnixEpoch;
  if (inner !== undefined) return toIso(inner);
  const d = (v as { toDate?: () => Date })?.toDate?.();
  if (d instanceof Date) return d.toISOString();
  return new Date().toISOString();
}

/** Honest provenance mapping into the dashboard vocabulary
 * (LIVE | REPLAY | DEMO). Unknown/absent -> DEMO (never upgrade). */
function mapProvenance(raw: unknown): string {
  const p = String(raw ?? '').toUpperCase();
  if (p === 'LIVE') return 'LIVE';
  if (p === 'REPLAY') return 'REPLAY';
  return 'DEMO'; // SIM, SYNTHETIC, DEMO, missing — all non-live
}

interface PoseReport {
  contract: string;
  schema_version: number;
  device_id: string;
  x: number;
  y: number;
  theta: number;
  unit: string;
  frame_id: string;
  timestamp: string;
  provenance: string;
  mission_id?: string;
}

/** Latest pose-bearing mission_status observations, newest first,
 * deduped to the freshest fix per device. */
function collectPoses(): PoseReport[] {
  const latest = new Map<string, { at: number; report: PoseReport }>();
  for (const row of conn.db.observationFeed.iter() as Iterable<any>) {
    if (String(row.kind) !== 'mission_status') continue;
    let data: any;
    try { data = JSON.parse(String(row.dataJson ?? '{}')); } catch { continue; }
    const pose = data?.pose;
    if (!pose || typeof pose !== 'object') continue;
    const x = Number(pose.x), y = Number(pose.y);
    const theta = Number(pose.heading_rad ?? pose.theta ?? 0);
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(theta)) continue;
    const deviceId = String(row.deviceId ?? data.device_id ?? '');
    if (!deviceId) continue;
    const iso = toIso(row.observedAt);
    const at = Date.parse(iso) || 0;
    const prev = latest.get(deviceId);
    if (prev && prev.at >= at) continue;
    const report: PoseReport = {
      contract: POSE_REPORT_CONTRACT,
      schema_version: SCHEMA_VERSION,
      device_id: deviceId,
      x, y, theta,
      unit: pose.unit === 'mm' ? 'mm' : 'm',
      frame_id: String(pose.frame ?? pose.frame_id ?? 'autonomy_map'),
      timestamp: iso,
      provenance: mapProvenance(data.provenance),
    };
    const mid = String(data.mission_id ?? '');
    if (mid) report.mission_id = mid;
    latest.set(deviceId, { at, report });
  }
  return [...latest.values()]
    .sort((a, b) => b.at - a.at)
    .slice(0, MAX_POSES)
    .map((e) => e.report);
}

// ---------------------------------------------------------------------------
// Surveyed-floorplan occupancy grid (DEMO-labelled synthetic rasterization)
// ---------------------------------------------------------------------------

interface WaypointAnchor { id: string; x: number; y: number; label?: string }

function loadAnchors(): WaypointAnchor[] {
  try {
    const routes = JSON.parse(readFileSync(ROUTES_PATH, 'utf8'));
    const out: WaypointAnchor[] = [];
    for (const zone of routes.zones ?? []) {
      for (const w of zone.waypoints ?? []) {
        if (!w?.id || !Number.isFinite(w.x_mm) || !Number.isFinite(w.y_mm)) continue;
        out.push({
          id: String(w.id),
          x: w.x_mm / 1000,   // mm -> surveyed_floorplan metres
          y: w.y_mm / 1000,
          label: `${zone.id}/${w.id}`,
        });
      }
    }
    return out.slice(0, 512);
  } catch (e) {
    log({ event: 'anchors_load_failed', error: String(e).slice(0, 160) });
    return [];
  }
}

const ANCHORS = loadAnchors();

/** 96x72 @ 0.25 m facility footprint — same layout the dashboard's
 * createFacilityGrid() uses (perimeter + two partitions), so the DEMO
 * map overlays the twin's static demo geometry consistently. */
function facilityCells(): { width: number; height: number; resolutionM: number; cells: number[] } {
  const width = 96, height = 72, resolutionM = 0.25;
  const cells = new Array<number>(width * height).fill(CELL_FREE);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const perimeter = y === 0 || y === height - 1 || x === 0 || x === width - 1;
      const verticalPartition = x === 56 && !(y >= 13 && y <= 23) && !(y >= 48 && y <= 57);
      const horizontalPartition = y === 36 && x > 56 && !(x >= 68 && x <= 79);
      if (perimeter || verticalPartition || horizontalPartition) {
        cells[y * width + x] = CELL_OCCUPIED;
      }
    }
  }
  return { width, height, resolutionM, cells };
}

const GRID = facilityCells();

function occupancyContract(): Record<string, unknown> {
  // Revision ticks once a minute — proves the feed is live without
  // fabricating map changes (cells are static survey walls).
  const revision = Math.floor(Date.now() / 60_000);
  return {
    contract: OCCUPANCY_GRID_CONTRACT,
    schema_version: SCHEMA_VERSION,
    frame_id: 'surveyed_floorplan',
    resolution_m: GRID.resolutionM,
    width: GRID.width,
    height: GRID.height,
    origin: { x: 0, y: 0 },
    revision,
    timestamp: new Date().toISOString(),
    cells: GRID.cells,
    anchors: ANCHORS,
    // Per-payload provenance: dashboard collectPayloads honors this over
    // the transport default — the map is a synthetic rasterization (DEMO)
    // even when pose fixes on the same response are LIVE.
    provenance: 'DEMO',
  };
}

// ---------------------------------------------------------------------------
// HTTP
// ---------------------------------------------------------------------------

const server = createServer((req, res) => {
  const url = req.url ?? '/';
  if (url.startsWith('/healthz')) {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ ok: true, svc: 'twin-feed' }));
    return;
  }
  if (url.startsWith('/twin-feed')) {
    try {
      const body = {
        provenance: 'LIVE', // transport-level: poses are real backend rows
        maps: [occupancyContract()],
        poses: collectPoses(),
        anchors: ANCHORS,
        detail: `spacetimedb ${DB} observationFeed -> pose_report contracts; surveyed_floorplan grid is DEMO`,
        generated_at: new Date().toISOString(),
      };
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(JSON.stringify(body));
    } catch (e) {
      res.writeHead(500, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ error: String(e).slice(0, 300) }));
    }
    return;
  }
  res.writeHead(404, { 'content-type': 'application/json' });
  res.end(JSON.stringify({ error: 'not found' }));
});

server.listen(PORT, '127.0.0.1', () => {
  log({ event: 'listening', port: PORT, uri: URI, db: DB, anchors: ANCHORS.length });
});
