// Fake implementations of the command adapter boundaries (issue #117).
// Every fake is deterministic, offline, and labels itself DEMO — a fake
// must never be mistaken for a live hardware/backend transport.

import type {
  AuthorizedMissionRequest, CommandAdapters, KismetReadAdapter,
  RoboticsCommandGateway, ROS2ReadAdapter, SourceEnvelope,
} from './adapters'
import type { Device, Observation, Point } from './model'
import type { AgentAssessment, InvestigationContext, NemotronTransport } from './agents'

let seq = 0
function envelope<T>(source: SourceEnvelope<T>['source'], provenance: SourceEnvelope<T>['provenance'], payload: T): SourceEnvelope<T> {
  seq += 1
  return { source, provenance, sequence: seq, timestamp: new Date(0).toISOString(), payload }
}

export class FakeRos2ReadAdapter implements ROS2ReadAdapter {
  private listeners = new Set<(m: SourceEnvelope<import('./adapters').RoverPoseMessage>) => void>()
  subscribePose(listener: (m: SourceEnvelope<import('./adapters').RoverPoseMessage>) => void) {
    this.listeners.add(listener)
    return () => { this.listeners.delete(listener) }
  }
  /** Test/demo hook: emit one pose fix. */
  emitPose(pose: import('./adapters').RoverPoseMessage, provenance: SourceEnvelope<never>['provenance'] = 'DEMO') {
    const msg = envelope('ros2', provenance, pose)
    for (const l of [...this.listeners]) l(msg)
  }
}

export class FakeKismetReadAdapter implements KismetReadAdapter {
  private listeners = new Set<(m: SourceEnvelope<Observation>) => void>()
  private devices: SourceEnvelope<Device[]> | null = null
  subscribeObservation(listener: (m: SourceEnvelope<Observation>) => void) {
    this.listeners.add(listener)
    return () => { this.listeners.delete(listener) }
  }
  listDevices() {
    return Promise.resolve(this.devices ?? envelope('kismet', 'DEMO', [] as Device[]))
  }
  /** Test/demo hooks. */
  emitObservation(obs: Observation, provenance: SourceEnvelope<never>['provenance'] = 'DEMO') {
    const msg = envelope('kismet', provenance, obs)
    for (const l of [...this.listeners]) l(msg)
  }
  setDevices(devices: Device[], provenance: SourceEnvelope<never>['provenance'] = 'DEMO') {
    this.devices = envelope('kismet', provenance, devices)
  }
}

export class FakeRoboticsCommandGateway implements RoboticsCommandGateway {
  readonly requests: AuthorizedMissionRequest[] = []
  constructor(private opts: { accept?: boolean; missionId?: string } = {}) {}
  requestMission(request: AuthorizedMissionRequest): Promise<{ accepted: boolean; missionId?: string; reason: string }> {
    this.requests.push(request)
    if (!request.requestId || !request.robotId || !request.operatorIdentity
      || !request.authorizationToken || !request.policyDecisionId
      || !Number.isFinite(request.target.x) || !Number.isFinite(request.target.y)) {
      return Promise.resolve({ accepted: false, reason: 'fake gateway: incomplete mission request' })
    }
    return Promise.resolve(this.opts.accept === false
      ? { accepted: false, reason: 'fake gateway: policy denied' }
      : { accepted: true, missionId: this.opts.missionId ?? `fake-mission-${this.requests.length}`, reason: 'accepted (fake — no dispatch)' })
  }
}

export class FakeNemotronTransport implements NemotronTransport {
  readonly contexts: InvestigationContext[] = []
  constructor(private assessment: Partial<AgentAssessment> = {}) {}
  infer(context: Readonly<InvestigationContext>): Promise<AgentAssessment> {
    this.contexts.push(structuredClone(context))
    return Promise.resolve({
      title: 'Fake assessment', severity: 'low', confidence: 0.5,
      summary: 'Deterministic fake Nemotron assessment — not a live inference.',
      requestIsolation: false, target: { x: 0, y: 0 },
      ...this.assessment,
    } as AgentAssessment)
  }
}

/** Assemble a full fake adapter set for tests/demos. */
export function fakeAdapters(overrides: Partial<CommandAdapters> = {}): CommandAdapters {
  return {
    ros2: new FakeRos2ReadAdapter(),
    kismet: new FakeKismetReadAdapter(),
    commands: new FakeRoboticsCommandGateway(),
    nemotron: new FakeNemotronTransport(),
    ...overrides,
  }
}

export type { Point }
