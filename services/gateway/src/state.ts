import { existsSync, readFileSync, writeFileSync } from 'node:fs';

// Restart-reconciliation state for the gateway worker. Everything here is
// derived from SpacetimeDB views, so losing the file only costs re-scanning;
// it exists to prevent duplicate MQTT publishes after a crash between
// "published command" and "markMissionDispatched".

export interface GatewayState {
  /** missionId -> 'published' once the MQTT command went out. */
  dispatchedMissions: Record<string, 'published'>;
  /** outboxId -> terminal outcome already reported (survives restarts). */
  completedOutbox: Record<string, 'succeeded' | 'failed'>;
  /** deviceId -> last gateway-assigned seq for normalized telemetry. */
  seqCounters: Record<string, string>;
}

export class StateStore {
  private state: GatewayState;

  constructor(private file: string) {
    this.state = existsSync(file)
      ? (JSON.parse(readFileSync(file, 'utf8')) as GatewayState)
      : { dispatchedMissions: {}, completedOutbox: {}, seqCounters: {} };
    this.state.seqCounters ??= {};
  }

  hasDispatched(missionId: string): boolean {
    return this.state.dispatchedMissions[missionId] === 'published';
  }

  markDispatched(missionId: string): void {
    this.state.dispatchedMissions[missionId] = 'published';
    this.flush();
  }

  hasCompletedOutbox(outboxId: string): boolean {
    return this.state.completedOutbox[outboxId] !== undefined;
  }

  /** Next monotonic seq for gateway-normalized device telemetry. */
  nextSeq(deviceId: string): bigint {
    const cur = BigInt(this.state.seqCounters[deviceId] ?? '0');
    const next = cur + 1n;
    this.state.seqCounters[deviceId] = next.toString();
    this.flush();
    return next;
  }

  markOutboxDone(outboxId: string, outcome: 'succeeded' | 'failed'): void {
    this.state.completedOutbox[outboxId] = outcome;
    this.flush();
  }

  private flush(): void {
    writeFileSync(this.file, JSON.stringify(this.state, null, 2));
  }
}
