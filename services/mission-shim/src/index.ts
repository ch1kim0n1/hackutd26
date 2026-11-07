// Mission shim — device-side bridge from the SpacetimeDB mission
// downlink to the rover's signed-mission file intake.
//
// Flow: gateway publishes module commandJson to
//   sentinel/v1/<device>/command
// shim (running on/near the rover, authenticated as the DEVICE) maps it
// to the rover contract, HMAC-signs it, and drops
//   <inbox>/<device>/<mission_id>.json
// Rover picks it up via `rover-mission run-mission` or `watch-missions`.
//
// Idempotent: an existing mission file is never overwritten — redelivery
// of the same mission_id is a no-op.

import { existsSync, mkdirSync, renameSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import mqtt from 'mqtt';
import { loadConfig, type DeviceShimConfig } from './config.js';
import { transformCommand } from './transform.js';

const config = loadConfig();

let delivered = 0;
let rejected = 0;

function deviceSecret(cfg: DeviceShimConfig): string {
  if (cfg.secret_env) {
    const v = process.env[cfg.secret_env];
    if (!v) throw new Error(`env ${cfg.secret_env} not set for device secret`);
    return v;
  }
  return config.signingSecret;
}

function safeName(id: string): string {
  return id.replace(/[^A-Za-z0-9_.-]/g, '_').slice(0, 128);
}

function handleCommand(deviceId: string, cfg: DeviceShimConfig, payload: Buffer): void {
  let raw: unknown;
  try {
    raw = JSON.parse(payload.toString('utf8'));
  } catch {
    rejected++;
    console.log(JSON.stringify({ event: 'reject', device: deviceId, reason: 'invalid json' }));
    return;
  }
  const secret = deviceSecret(cfg);
  const result = transformCommand(raw, deviceId, cfg, secret);
  if (!result.ok) {
    rejected++;
    console.log(JSON.stringify({ event: 'reject', device: deviceId, reason: result.reason }));
    return;
  }
  const missionId = String(result.mission.mission_id);
  const dir = join(config.inboxDir, deviceId);
  mkdirSync(dir, { recursive: true });
  const dest = join(dir, `${safeName(missionId)}.json`);
  if (existsSync(dest)) {
    console.log(JSON.stringify({ event: 'dup', device: deviceId, mission: missionId }));
    return;
  }
  const tmp = `${dest}.tmp-${process.pid}`;
  writeFileSync(tmp, JSON.stringify(result.mission, null, 2));
  renameSync(tmp, dest); // atomic — rover never sees a partial file
  delivered++;
  console.log(JSON.stringify({ event: 'delivered', device: deviceId, mission: missionId, type: result.mission.type }));
}

for (const [deviceId, cfg] of Object.entries(config.devices)) {
  const topic = config.commandTopic.replace('{device}', deviceId);
  const client = mqtt.connect(config.mqttUrl, {
    username: cfg.mqtt_username ?? config.mqttUsername,
    password: cfg.mqtt_password ?? config.mqttPassword,
    clientId: `mission-shim-${deviceId}`,
    reconnectPeriod: 2000,
  });
  client.on('connect', () => {
    console.log(JSON.stringify({ event: 'mqtt_connect', device: deviceId, topic }));
    client.subscribe(topic, { qos: 1 }, (err) => {
      if (err) console.log(JSON.stringify({ event: 'subscribe_error', device: deviceId, error: String(err) }));
    });
  });
  client.on('message', (t, payload) => {
    if (t !== topic) return;
    try {
      handleCommand(deviceId, cfg, payload);
    } catch (err) {
      rejected++;
      console.log(JSON.stringify({ event: 'error', device: deviceId, error: String(err).slice(0, 200) }));
    }
  });
  client.on('error', (err) => {
    console.log(JSON.stringify({ event: 'mqtt_error', device: deviceId, error: String(err).slice(0, 200) }));
  });
}

console.log(JSON.stringify({
  event: 'shim_ready',
  devices: Object.keys(config.devices),
  inbox: config.inboxDir,
}));
