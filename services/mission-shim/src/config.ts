export interface DeviceShimConfig {
  /** Rover camera mount id for capture_photo missions. Default 'cam-mast'
   *  (the only mount known to robotics/rover/config/routes.json). */
  camera_id?: string;
  /** module waypoint_id (or '*') -> rover route_id for patrol missions. */
  routes?: Record<string, string>;
  /** Env var holding this device's HMAC secret. Default SHIM_SIGNING_SECRET. */
  secret_env?: string;
  /** Per-device broker credentials (ACL: device reads only its own
   *  command topic). Falls back to global MQTT_USERNAME/MQTT_PASSWORD. */
  mqtt_username?: string;
  mqtt_password?: string;
}

export interface ShimConfig {
  /** device_id -> shim config. Only listed devices get signed missions. */
  devices: Record<string, DeviceShimConfig>;
  mqttUrl: string;
  mqttUsername?: string;
  mqttPassword?: string;
  /** Command topic template; {device} is substituted. */
  commandTopic: string;
  inboxDir: string;
  signingSecret: string;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): ShimConfig {
  const devicesJson = env.SHIM_DEVICES;
  if (!devicesJson) throw new Error('missing required env SHIM_DEVICES');
  let devices: Record<string, DeviceShimConfig>;
  try {
    devices = JSON.parse(devicesJson) as Record<string, DeviceShimConfig>;
  } catch {
    throw new Error('SHIM_DEVICES is not valid JSON');
  }
  if (Object.keys(devices).length === 0) {
    throw new Error('SHIM_DEVICES must list at least one device');
  }
  const mqttUrl = env.MQTT_URL;
  if (!mqttUrl) throw new Error('missing required env MQTT_URL');
  const signingSecret = env.SHIM_SIGNING_SECRET;
  if (!signingSecret) throw new Error('missing required env SHIM_SIGNING_SECRET');
  return {
    devices,
    mqttUrl,
    mqttUsername: env.MQTT_USERNAME,
    mqttPassword: env.MQTT_PASSWORD,
    commandTopic: env.SHIM_COMMAND_TOPIC ?? 'sentinel/v1/{device}/command',
    inboxDir: env.SHIM_INBOX_DIR ?? './mission-inbox',
    signingSecret,
  };
}
