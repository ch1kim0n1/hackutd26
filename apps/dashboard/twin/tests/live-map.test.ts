import { describe, expect, it } from 'vitest'
import { fixtureSnapshot } from '../src/command/live/fixture'
import { mapSnapshot, mapObservationKind, mapZones, mapDevices, mapIncidents, mapEvidence, mapFindings, mapMissions, mapApprovals, mapEvents, mapActivity, mapTelemetry, mapRover } from '../src/command/live/map'
import { backendToElapsed, toMicros } from '../src/command/live/time'
import { emptyRows, type LiveRows, type LiveSnapshot } from '../src/command/live/types'
import type { MapContext } from '../src/command/live/map'

const ctx: MapContext = { elapsed: 100, backendNowMicros: 1_760_000_000_000_000, provenance: 'REPLAY' }
const snap = fixtureSnapshot()

function poseObs(id: number, seq: number, pose: Record<string, unknown>, observedAtMicros: number): Record<string, unknown> {
  return {
    id, eventId: `pose-${id}`, deviceId: 'rover-01', kind: 'mission_status',
    seq, observedAt: observedAtMicros, receivedAt: observedAtMicros,
    zoneId: 'ops-floor',
    dataJson: JSON.stringify({ mission_id: 'sim-patrol', state: 'navigating',
      provenance: 'SIM',
      pose: { unit: 'm', frame: 'autonomy_map', source: 'autonomy_sim', ...pose } }),
    trustTier: { tag: 'GatewayValidated' }, traceId: 't',
  }
}

describe('live mappers', () => {
  it('maps zones from boundsJson', () => {
    const zones = mapZones(snap.rows.zones)
    expect(zones).toHaveLength(3)
    expect(zones[0].bounds).toEqual([0, 0, 14, 18])
    expect(zones[0].position).toEqual({ x: 7, y: 9 })
  })

  it('maps devices with kind/status/provenance-safe fields', () => {
    const devices = mapDevices(snap.rows, ctx)
    expect(devices).toHaveLength(5)
    expect(devices.find(d => d.id === 'puck-ble-01')?.kind).toBe('ble')
    expect(devices.find(d => d.id === 'puck-ble-01')?.status).toBe('watch')
    expect(devices.find(d => d.id === 'rover-01')?.kind).toBe('rover')
    for (const d of devices) expect(d.signalHistory).toHaveLength(24)
  })

  it('classifies observation kinds and prefixes provenance', () => {
    expect(mapObservationKind('ble_observation', '{}')).toBe('unknown')
    expect(mapObservationKind('wifi_observation', '{"ssid":"x"}')).toBe('impersonation')
    expect(mapObservationKind('cabinet_contact_open', '{}')).toBe('tamper')
    const obs = mapSnapshot(snap, 100).entities.observations
    expect(obs.length).toBe(3)
    expect(obs[0].detail).toMatch(/^REPLAY · /)
    expect(new Set(obs.map(o => o.id)).size).toBe(obs.length)
  })

  it('joins incident → alerts → observations for zone/device links', () => {
    const incidents = mapIncidents(snap.rows, ctx)
    expect(incidents).toHaveLength(1)
    const inc = incidents[0]
    expect(inc.zoneId).toBe('rack-hall')
    expect(inc.deviceIds).toEqual(['puck-ble-01'])
    expect(inc.observationIds).toEqual(['obs-evt-fixture-002'])
    expect(inc.evidenceIds).toEqual(['ev-evd-fixture-001'])
    expect(inc.findingIds).toEqual(['fnd-scope-fixture-001'])
    expect(inc.timeline.length).toBeGreaterThanOrEqual(3)
    expect(inc.status).toBe('investigating')
  })

  it('maps evidence, findings, missions, approvals deterministically', () => {
    const ev = mapEvidence(snap.rows.evidence, ctx)
    expect(ev[0].id).toBe('ev-evd-fixture-001')
    expect(ev[0].incidentId).toBe('inc-fixture-001')
    expect(ev[0].type).toBe('rf')
    const fnd = mapFindings(snap.rows.scopeEntries, ctx)
    expect(fnd[0].confidence).toBe(0.6)
    expect(fnd[0].evidenceIds).toEqual(['ev-evd-fixture-001'])
    expect(mapMissions(snap.rows, ctx)).toEqual([])
    expect(mapApprovals(snap.rows, ctx)).toEqual([])
  })

  it('maps approvals+actions join with pending/decided status', () => {
    const rows: LiveRows = { ...emptyRows(), incidents: snap.rows.incidents }
    rows.actions = [{ id: 'act-1', incidentId: 'inc-fixture-001', type: { tag: 'IsolateEndpoint' }, targetId: 'puck-ble-01', state: { tag: 'PendingApproval' }, reason: 'test', payloadJson: '{}', resultJson: '{}', traceId: 't', createdAt: 1_760_000_000_000_000 - 5_000_000, updatedAt: 0, version: 1n, proposerId: 'agent', approverId: '' } as never]
    rows.approvals = [{ id: 'appr-1', actorId: 'cmd', actionId: 'act-1', decision: { tag: 'Approved' }, expiresAt: 0, decidedAt: 1_760_000_000_000_000 - 4_000_000, note: '', traceId: 't' } as never]
    const approvals = mapApprovals(rows, ctx)
    expect(approvals).toHaveLength(1)
    expect(approvals[0].status).toBe('approved')
    expect(approvals[0].targetId).toBe('puck-ble-01')
  })

  it('maps alerts+audit to events and activity with stable dedupe ids', () => {
    const events = mapEvents(snap.rows, ctx)
    const activity = mapActivity(snap.rows, snap.api.investigations, ctx)
    expect(events.map(e => e.id)).toContain('alert-alert-fixture-001')
    expect(events.map(e => e.id)).toContain('aud-aud-fixture-001')
    expect(activity.map(a => a.id)).toContain('inv-api-incident-1-0')
    expect(new Set(events.map(e => e.id)).size).toBe(events.length)
    expect(new Set(activity.map(a => a.id)).size).toBe(activity.length)
  })

  it('derives telemetry deterministically from rows only', () => {
    const t1 = mapTelemetry(snap.rows, ctx)
    const t2 = mapTelemetry(snap.rows, ctx)
    expect(t1).toEqual(t2)
    expect(t1).toHaveLength(24)
    expect(t1.every(s => s.cpu === 0 && s.latency === 0)).toBe(true)
    expect(t1.at(-1)!.traffic).toBeGreaterThan(0) // fixture obs in recent bucket
  })

  it('parks rover at zone anchor flagged stale without pose telemetry', () => {
    const rover = mapRover(snap.rows, ctx, [])
    expect(rover.position.x).toBeGreaterThan(0)
    expect(rover.battery).toBe(100)
    expect(rover.stale).toBe(true)
    expect(rover.speed).toBe(0)
  })

  it('renders rover pose purely from mission_status telemetry', () => {
    const rows = { ...snap.rows, observations: [
      ...snap.rows.observations,
      poseObs(1, 1, { x: 0.5, y: -0.25, heading_rad: 0.3 }, 1_760_000_000_000_000 - 1_000_000),
      poseObs(2, 2, { x: 1.0, y: -0.25, heading_rad: 0.3 }, 1_760_000_000_000_000 - 500_000),
    ] }
    const rover = mapRover(rows as never, ctx, [])
    // autonomy_map frame -> sim room registered at facility centre (12,9)
    expect(rover.position.x).toBeCloseTo(13.0)
    expect(rover.position.y).toBeCloseTo(8.75)
    expect(rover.heading).toBeCloseTo(0.3)
    expect(rover.stale).toBe(false)
    // 0.5 m over 0.5 s -> ~1 m/s, capped at 3
    expect(rover.speed).toBeCloseTo(1.0)
  })

  it('marks rover stale when pose telemetry stops', () => {
    const rows = { ...snap.rows, observations: [
      poseObs(1, 1, { x: 0.5, y: 0, heading_rad: 0 }, 1_760_000_000_000_000 - 10_000_000),
    ] }
    const rover = mapRover(rows as never, ctx, [])
    expect(rover.stale).toBe(true)
    expect(rover.speed).toBe(0)
  })

  it('uses surveyed-frame rover poses without the sim transform', () => {
    const rows = { ...snap.rows, observations: [
      { ...poseObs(1, 1, { x_mm: 5000, y_mm: -2500, heading_rad: 1.2 }, 1_760_000_000_000_000 - 1_000_000),
        dataJson: JSON.stringify({ mission_id: 'm-1', state: 'navigating',
          pose: { x_mm: 5000, y_mm: -2500, heading_rad: 1.2, confidence: 0.9, source: 'apriltag' } }) },
    ] }
    const rover = mapRover(rows as never, ctx, [])
    expect(rover.position.x).toBeCloseTo(5)
    expect(rover.position.y).toBeCloseTo(-2.5)
    expect(rover.heading).toBeCloseTo(1.2)
  })

  it('ignores non-pose mission_status and other devices', () => {
    const rows = { ...snap.rows, observations: [
      { ...poseObs(1, 1, { x: 9, y: 9, heading_rad: 0 }, 1_760_000_000_000_000 - 1_000_000),
        deviceId: 'puck-wifi-01' },
      { ...poseObs(2, 2, { x: 9, y: 9, heading_rad: 0 }, 1_760_000_000_000_000 - 1_000_000),
        dataJson: '{"mission_id":"m","state":"completed"}' },
    ] }
    const rover = mapRover(rows as never, ctx, [])
    expect(rover.stale).toBe(true) // no usable rover-01 pose
  })

  it('produces identical entities on snapshot replay (resync-safe)', () => {
    const a = mapSnapshot(snap, 100).entities
    const b = mapSnapshot(snap, 100).entities
    expect(a).toEqual(b)
    // Re-mapping the same backend rows can never duplicate ids.
    for (const list of [a.observations, a.incidents, a.evidence, a.findings, a.missions, a.approvals, a.events, a.activity]) {
      const ids = list.map(e => e.id)
      expect(new Set(ids).size).toBe(ids.length)
    }
  })
})

describe('time mapping', () => {
  it('converts bigint/number micros', () => {
    expect(toMicros(1_760_000_000_000_000n)).toBe(1_760_000_000_000_000)
    expect(toMicros(1_760_000_000_000_000)).toBe(1_760_000_000_000_000)
    expect(toMicros(1_760_000_000_000)).toBe(1_760_000_000_000_000) // millis heuristic
  })
  it('maps backend time to elapsed preserving age', () => {
    const now = 1_760_000_000_000_000
    expect(backendToElapsed(now - 10_000_000, 100, now)).toBeCloseTo(90)
    expect(backendToElapsed(now + 5_000_000, 100, now)).toBe(100) // future clamped
    expect(backendToElapsed(0, 100, now)).toBe(100)
  })
})
