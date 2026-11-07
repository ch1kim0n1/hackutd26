export interface GatewayConfig {
  spacetimedbUri: string;
  database: string;
  /** Auth token for the `gateway`-role identity (see deploy/seeds). */
  spacetimedbToken: string;
  /** Optional second identity with the `executor` role for the outbox worker. */
  executorSpacetimedbToken?: string;
  mqttUrl: string;
  mqttUsername?: string;
  mqttPassword?: string;
  /** Topic prefix; devices publish to `<prefix>/<device_id>/telemetry`. */
  topicPrefix: string;
  /** Optional lab executor webhook for approved actions (issue #17 outbox). */
  executorWebhookUrl?: string;
  executorWebhookToken?: string;
  healthPort: number;
  stateFile: string;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): GatewayConfig {
  const required = (name: string): string => {
    const v = env[name];
    if (!v) throw new Error(`missing required env ${name}`);
    return v;
  };
  return {
    spacetimedbUri: env.SPACETIMEDB_URI ?? 'ws://127.0.0.1:3000',
    database: required('SPACETIMEDB_DATABASE'),
    spacetimedbToken: required('SPACETIMEDB_TOKEN'),
    executorSpacetimedbToken: env.EXECUTOR_SPACETIMEDB_TOKEN,
    mqttUrl: required('MQTT_URL'),
    mqttUsername: env.MQTT_USERNAME,
    mqttPassword: env.MQTT_PASSWORD,
    topicPrefix: env.MQTT_TOPIC_PREFIX ?? 'sentinel/v1',
    executorWebhookUrl: env.EXECUTOR_WEBHOOK_URL,
    executorWebhookToken: env.EXECUTOR_WEBHOOK_TOKEN,
    healthPort: Number(env.GATEWAY_HEALTH_PORT ?? 8081),
    stateFile: env.GATEWAY_STATE_FILE ?? './gateway-state.json',
  };
}
