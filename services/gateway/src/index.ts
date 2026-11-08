import http from 'node:http';
import mqtt from 'mqtt';
import { DbConnection } from '../bindings/index';
import { loadConfig } from './config.js';
import { normalizeTelemetry, topicDeviceId } from './validate.js';
import { StateStore } from './state.js';

// SENTINEL HIVE gateway — the single constrained bridge between the
// untrusted lab network and the Winstead command plane (docs/01, docs/06).
//
//   lab device --MQTT--> this service --ingestObservation--> SpacetimeDB
//   SpacetimeDB pendingMissions --> MQTT command --> rover
//   SpacetimeDB executorOutbox --> webhook/executor --> recordExecutorOutcome
//
// Two least-privilege SpacetimeDB identities are used:
//   - `gateway` token: telemetry ingest + mission downlink views/reducers
//   - `executor` token: action outbox claim/outcome (optional; worker disabled
//     without it so the ingest path can run standalone in tests)
// All authorization happens inside reducers via ctx.sender; this process
// never asserts roles itself.

const config = loadConfig();
const state = new StateStore(config.stateFile);

const stats = {
  ingested: 0,
  rejected: 0,
  dispatched: 0,
  outboxDone: 0,
  eventsForwarded: 0,
  lastIngestAt: 0,
  lastError: '',
};
let mqttConnected = false;
let stdConnected = false;
let executorConnected = false;

function connectDb(token: string | undefined, onUp: () => void): Promise<DbConnection> {
  return new Promise((resolve, reject) => {
    let b = DbConnection.builder()
      .withUri(config.spacetimedbUri)
      .withDatabaseName(config.database)
      .withAutomaticReconnect();
    if (token) b = b.withToken(token);
    b.onConnect((c) => {
      onUp();
      resolve(c);
    })
      .onConnectError((_ctx, err) => {
        stats.lastError = `std connect: ${String(err)}`;
        reject(err);
      })
      .build();
  });
}

const conn = await connectDb(config.spacetimedbToken, () => {
  stdConnected = true;
});
conn.subscriptionBuilder().subscribe((tb) => tb.pendingMissions.build());

// Executor worker identity — separate connection so outbox claims carry the
// `executor` role, not the gateway role.
let execConn: DbConnection | null = null;
if (config.executorSpacetimedbToken) {
  execConn = await connectDb(config.executorSpacetimedbToken, () => {
    executorConnected = true;
  });
  execConn.subscriptionBuilder().subscribe((tb) => tb.executorOutbox.build());
} else {
  console.log('EXECUTOR_SPACETIMEDB_TOKEN not set — outbox worker disabled');
}

// ---------------------------------------------------------------------------
// MQTT ingest path
// ---------------------------------------------------------------------------

const mqttClient = mqtt.connect(config.mqttUrl, {
  username: config.mqttUsername,
  password: config.mqttPassword,
  reconnectPeriod: 2000,
  clientId: `sentinel-gateway-${process.pid}`,
});

mqttClient.on('connect', () => {
  mqttConnected = true;
  mqttClient.subscribe(`${config.topicPrefix}/+/telemetry`, { qos: 1 }, (err) => {
    if (err) stats.lastError = `mqtt subscribe: ${err.message}`;
  });
});
mqttClient.on('close', () => {
  mqttConnected = false;
});
mqttClient.on('error', (err) => {
  stats.lastError = `mqtt: ${err.message}`;
});

mqttClient.on('message', (topic, payload) => {
  void handleTelemetry(topic, payload).catch((err) => {
    stats.rejected++;
    stats.lastError = `ingest: ${String(err).slice(0, 200)}`;
  });
});

async function handleTelemetry(topic: string, payload: Buffer): Promise<void> {
  const deviceId = topicDeviceId(topic, config.topicPrefix);
  if (deviceId === null) {
    stats.rejected++;
    return; // not a telemetry topic shape we own
  }
  const result = normalizeTelemetry(payload, deviceId, config.deviceHmacKeys);
  if (!result.ok) {
    stats.rejected++;
    stats.lastError = `reject ${topic}: ${result.reason}`;
    return;
  }
  const v = result.value;
  // Rover-normalized events carry seq=0n -> assign the persisted per-device
  // monotonic seq so SpacetimeDB replay protection still applies.
  const seq = v.seqAssigned ? state.nextSeq(v.deviceId) : v.seq;
  await conn.reducers.ingestObservation({
    eventId: v.eventId,
    deviceId: v.deviceId,
    kind: v.kind,
    seq,
    observedAtMicros: v.observedAtMicros,
    zoneId: v.zoneId,
    dataJson: v.dataJson,
    trustTier: 'gateway_validated',
    traceId: v.traceId || `mqtt:${topic}`,
  });
  stats.ingested++;
  stats.lastIngestAt = Date.now();
  void notifyInvestigation(v);
}

// Issue #112: forward accepted observations to the investigator
// orchestrator so Nemotron investigates without manual prompting.
// Fire-and-forget — investigation latency must never stall ingest.
function notifyInvestigation(v: {
  eventId: string; deviceId: string; kind: string; zoneId: string;
  observedAtMicros: bigint; dataJson: string; traceId: string;
}): void {
  if (!config.investigationEventUrl) return;
  const body = JSON.stringify({
    event_id: v.eventId,
    kind: v.kind,
    source: 'observation',
    device_id: v.deviceId,
    zone_id: v.zoneId,
    provenance: 'LIVE',
    observed_at: new Date(Number(v.observedAtMicros) / 1000).toISOString(),
    summary: `${v.kind} on ${v.deviceId}`,
    data: { seq_trace: v.traceId, payload: v.dataJson.slice(0, 500) },
  });
  fetch(config.investigationEventUrl, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      ...(config.investigationEventToken
        ? { authorization: `Bearer ${config.investigationEventToken}` }
        : {}),
    },
    body,
    signal: AbortSignal.timeout(2_000),
  }).then((res) => {
    if (res.ok) stats.eventsForwarded++;
    else stats.lastError = `orch event ${res.status}`;
  }).catch((err) => {
    stats.lastError = `orch event: ${String(err).slice(0, 120)}`;
  });
}

// ---------------------------------------------------------------------------
// Mission downlink: approved missions -> MQTT command -> markMissionDispatched
// ---------------------------------------------------------------------------

async function dispatchMissions(): Promise<void> {
  for (const m of conn.db.pendingMissions.iter() as Iterable<any>) {
    const missionId = m.id as string;
    if (state.hasDispatched(missionId)) {
      // Published before a possible crash: reconcile the DB marker only.
      try {
        await conn.reducers.markMissionDispatched({ missionId });
      } catch {
        /* already dispatched/expired — view will drop it */
      }
      continue;
    }
    const topic = `${config.topicPrefix}/${m.deviceId}/command`;
    // commandJson is the canonical contract built inside the reducer tx.
    await new Promise<void>((resolve, reject) => {
      mqttClient.publish(topic, m.commandJson, { qos: 1, retain: false }, (err) =>
        err ? reject(err) : resolve()
      );
    });
    // Record intent BEFORE marking dispatched: if we crash here, restart sees
    // hasDispatched() and only reconciles markMissionDispatched — the rover
    // dedupes on command_id/mission_id anyway.
    state.markDispatched(missionId);
    try {
      await conn.reducers.markMissionDispatched({ missionId });
      stats.dispatched++;
    } catch {
      /* mission expired/cancelled between view and call — fine */
    }
  }
}

// ---------------------------------------------------------------------------
// Action outbox worker: claim -> execute -> record outcome (executor identity)
// ---------------------------------------------------------------------------

async function executeOutbox(): Promise<void> {
  if (!execConn) return;
  for (const row of execConn.db.executorOutbox.iter() as Iterable<any>) {
    const outboxId = String(row.id);
    const stateTag = String(row.state?.tag ?? row.state).toLowerCase();
    if (stateTag !== 'pending' && stateTag !== 'claimed') continue;
    if (state.hasCompletedOutbox(outboxId)) continue;

    const claimedId = BigInt(outboxId);
    if (stateTag === 'pending') {
      try {
        await execConn.reducers.claimOutbox({ outboxId: claimedId });
      } catch {
        continue; // someone else claimed or row vanished
      }
    }
    // 'claimed' rows survive restarts: the DB claim is already ours to finish,
    // and recordExecutorOutcome is idempotent against double-report.

    const { outcome, verificationRef, resultJson } = await runExecutor(row);
    try {
      await execConn.reducers.recordExecutorOutcome({
        outboxId: claimedId,
        outcome,
        verificationRef,
        resultJson,
      });
      state.markOutboxDone(outboxId, outcome);
      stats.outboxDone++;
    } catch {
      /* outcome already recorded by a previous run — idempotent skip */
    }
  }
}

async function runExecutor(row: any): Promise<{
  outcome: 'succeeded' | 'failed';
  verificationRef: string;
  resultJson: string;
}> {
  // Lab executor: forward the approved payload to the configured webhook
  // (firewall/VLAN lab endpoint). No webhook configured -> record a synthetic
  // lab acknowledgement so the pipeline is still exercisable end-to-end.
  if (!config.executorWebhookUrl) {
    return {
      outcome: 'succeeded',
      verificationRef: 'lab-noop-executor',
      resultJson: JSON.stringify({ simulated: true, actionId: row.actionId }),
    };
  }
  try {
    const res = await fetch(config.executorWebhookUrl, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        ...(config.executorWebhookToken
          ? { authorization: `Bearer ${config.executorWebhookToken}` }
          : {}),
      },
      body: row.payloadJson,
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok) throw new Error(`webhook ${res.status}`);
    return {
      outcome: 'succeeded',
      verificationRef: `webhook:${res.status}`,
      resultJson: JSON.stringify({ httpStatus: res.status, actionId: row.actionId }),
    };
  } catch (err) {
    return {
      outcome: 'failed',
      verificationRef: 'webhook-error',
      resultJson: JSON.stringify({ error: String(err).slice(0, 300), actionId: row.actionId }),
    };
  }
}

// ---------------------------------------------------------------------------
// Health + main loop
// ---------------------------------------------------------------------------

const server = http.createServer((req, res) => {
  if (req.url === '/healthz') {
    const ok = mqttConnected && stdConnected;
    res.writeHead(ok ? 200 : 503, { 'content-type': 'application/json' });
    res.end(
      JSON.stringify({
        ok,
        mqttConnected,
        stdConnected,
        executorConnected,
        stats,
        uptimeSec: Math.floor(process.uptime()),
      })
    );
    return;
  }
  res.writeHead(404);
  res.end();
});
server.listen(config.healthPort, () => {
  console.log(`gateway health on :${config.healthPort}`);
});

const TICK_MS = 1000;
setInterval(() => {
  dispatchMissions().catch((e) => {
    stats.lastError = `dispatch: ${String(e).slice(0, 200)}`;
  });
  executeOutbox().catch((e) => {
    stats.lastError = `outbox: ${String(e).slice(0, 200)}`;
  });
}, TICK_MS);

console.log(
  `sentinel-hive gateway up: db=${config.database} mqtt=${config.mqttUrl} prefix=${config.topicPrefix}`
);
