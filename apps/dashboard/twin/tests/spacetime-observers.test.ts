import { expect, it, vi } from 'vitest'
import { observeTables } from '../src/command/live/spacetime'

it('observes inserts, updates and deletes, then detaches on stop', () => {
  const listeners = new Map<string, () => void>()
  const table = {
    onInsert: (cb: () => void) => { listeners.set('insert', cb) },
    onUpdate: (cb: () => void) => { listeners.set('update', cb) },
    onDelete: (cb: () => void) => { listeners.set('delete', cb) },
    removeOnInsert: vi.fn(), removeOnUpdate: vi.fn(), removeOnDelete: vi.fn(),
  }
  const changed = vi.fn()
  const stop = observeTables({ observationFeed: table }, changed)
  listeners.get('insert')?.(); listeners.get('update')?.(); listeners.get('delete')?.()
  expect(changed).toHaveBeenCalledTimes(3)
  stop()
  expect(table.removeOnInsert).toHaveBeenCalledWith(changed)
  expect(table.removeOnUpdate).toHaveBeenCalledWith(changed)
  expect(table.removeOnDelete).toHaveBeenCalledWith(changed)
})
