import { expect, it } from 'vitest'
import { contextBrief } from '../src/command/context-brief'
import { advanceSimulation, changeSimulation, createInitialState, setEmergencyStop } from '../src/command/engine'
it('the optional context brief reflects current shared evidence, selection, and safety state', () => {
  const state = advanceSimulation(changeSimulation(createInitialState(), 'start'), 45)
  expect(contextBrief(state, 'ble-04')).toContain('Authorized maintenance explains the anomaly')
  expect(contextBrief(state, 'ble-04')).toContain('5 linked evidence records')
  expect(contextBrief(state, 'rack-01')).toContain('SRV-01')
  expect(contextBrief(setEmergencyStop(state,true), null, 'rover status')).toContain('halted by the independent emergency stop')
})
