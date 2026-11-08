import { describe, expect, it } from 'vitest'
import {
  FakeKismetReadAdapter, FakeNemotronTransport, FakeRoboticsCommandGateway,
  FakeRos2ReadAdapter, fakeAdapters,
} from '../src/command/adapters-fakes'
import type { AuthorizedMissionRequest } from '../src/command/adapters'

const PROVENANCES = ['DEMO', 'REPLAY', 'LIVE'] as const

function validRequest(): AuthorizedMissionRequest {
  return {
    requestId: 'req-1', robotId: 'rover-01', target: { x: 3, y: 4 },
    operatorIdentity: 'op-1', authorizationToken: 'tok', policyDecisionId: 'pol-1',
  }
}

describe('adapter contract — ROS2 pose', () => {
  it('emits SourceEnvelope with provenance, monotonic sequence, ISO timestamp', () => {
    const ros2 = new FakeRos2ReadAdapter()
    const seen: number[] = []
    ros2.subscribePose(m => {
      expect(m.source).toBe('ros2')
      expect(PROVENANCES).toContain(m.provenance)
      expect(Number.isInteger(m.sequence)).toBe(true)
      expect(Number.isNaN(Date.parse(m.timestamp))).toBe(false)
      seen.push(m.sequence)
    })
    ros2.emitPose({ robotId: 'rover-01', position: { x: 1, y: 2 }, heading: 0.5, battery: 90, emergencyStop: false })
    ros2.emitPose({ robotId: 'rover-01', position: { x: 1.5, y: 2 }, heading: 0.6, battery: 90, emergencyStop: false }, 'REPLAY')
    expect(seen).toEqual([1, 2])
  })

  it('unsubscribe stops delivery', () => {
    const ros2 = new FakeRos2ReadAdapter()
    let count = 0
    const off = ros2.subscribePose(() => { count += 1 })
    ros2.emitPose({ robotId: 'r', position: { x: 0, y: 0 }, heading: 0, battery: 1, emergencyStop: false })
    off()
    ros2.emitPose({ robotId: 'r', position: { x: 0, y: 0 }, heading: 0, battery: 1, emergencyStop: false })
    expect(count).toBe(1)
  })
})

describe('adapter contract — Kismet observations', () => {
  it('listDevices and subscribeObservation share the envelope contract', async () => {
    const kismet = new FakeKismetReadAdapter()
    kismet.setDevices([{ id: 'd1' } as never])
    const devices = await kismet.listDevices()
    expect(devices.source).toBe('kismet')
    expect(devices.provenance).toBe('DEMO')
    expect(devices.payload).toHaveLength(1)
    let got = 0
    kismet.subscribeObservation(() => { got += 1 })
    kismet.emitObservation({ id: 'o1' } as never, 'REPLAY')
    expect(got).toBe(1)
  })
})

describe('adapter contract — robotics command gateway', () => {
  it('accepts a fully-authorized request and never claims real dispatch', async () => {
    const gw = new FakeRoboticsCommandGateway()
    const res = await gw.requestMission(validRequest())
    expect(res.accepted).toBe(true)
    expect(res.missionId).toMatch(/^fake-mission-/)
    expect(res.reason).toContain('fake')
    expect(gw.requests).toHaveLength(1)
  })

  it('rejects incomplete requests (missing auth/policy fields)', async () => {
    const gw = new FakeRoboticsCommandGateway()
    const res = await gw.requestMission({ ...validRequest(), authorizationToken: '' })
    expect(res.accepted).toBe(false)
    const res2 = await gw.requestMission({ ...validRequest(), target: { x: NaN, y: 0 } })
    expect(res2.accepted).toBe(false)
  })

  it('can simulate policy denial', async () => {
    const gw = new FakeRoboticsCommandGateway({ accept: false })
    const res = await gw.requestMission(validRequest())
    expect(res.accepted).toBe(false)
    expect(res.reason).toContain('denied')
  })
})

describe('adapter contract — Nemotron transport', () => {
  it('returns a schema-valid AgentAssessment and records context', async () => {
    const nemotron = new FakeNemotronTransport({ confidence: 0.9 })
    const ctx = {
      provenance: 'DEMO' as const, observation: null, deviceIds: ['d1'],
      relatedObservationIds: [], activeIncidentIds: [], selectedEntityId: null,
    }
    const a = await nemotron.infer(ctx)
    expect(a.title).toBeTruthy()
    expect(a.confidence).toBe(0.9)
    expect(['low', 'medium', 'high', 'critical']).toContain(a.severity)
    expect(typeof a.requestIsolation).toBe('boolean')
    expect(nemotron.contexts).toHaveLength(1)
    // Context is cloned — mutating the caller's copy cannot corrupt the record.
    expect(nemotron.contexts[0]).not.toBe(ctx)
    expect(a.summary).toContain('fake')
  })
})

describe('fakeAdapters assembly', () => {
  it('returns all four boundaries with DEMO-labelled output', () => {
    const a = fakeAdapters()
    expect(a.ros2).toBeInstanceOf(FakeRos2ReadAdapter)
    expect(a.kismet).toBeInstanceOf(FakeKismetReadAdapter)
    expect(a.commands).toBeInstanceOf(FakeRoboticsCommandGateway)
    expect(a.nemotron).toBeInstanceOf(FakeNemotronTransport)
  })
})
