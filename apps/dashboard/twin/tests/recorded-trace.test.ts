import { describe, expect, it } from 'vitest'
import { RECORDED_TRACES, assertTraceComplete } from '../src/command/recordedTrace'

describe('recorded scenario traces (#114)', () => {
  it('ships all three scenarios', () => {
    expect(Object.keys(RECORDED_TRACES).sort()).toEqual([
      'interception', 'mitigation', 'prevention',
    ])
  })

  it.each(Object.entries(RECORDED_TRACES))(
    '%s trace is complete and labeled',
    (_name, trace) => {
      expect(() => assertTraceComplete(trace)).not.toThrow()
      expect(trace.ok).toBe(true)
      expect(trace.label).toBe('MOCK')
      expect(trace.provenance).toBe('DEMO')
      expect(trace.steps.length).toBeGreaterThan(0)
      expect(trace.agent_summary.length).toBeGreaterThan(20)
      expect(trace.uncertainty.length).toBeGreaterThan(0)
    },
  )
})
