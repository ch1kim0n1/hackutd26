import type { CommandEvent } from './model'

/** In-process event delivery only; state remains the canonical replayable record. */
export class CommandEventBus {
  private listeners = new Set<(event: Readonly<CommandEvent>) => void>()
  subscribe(listener: (event: Readonly<CommandEvent>) => void) { this.listeners.add(listener); return () => { this.listeners.delete(listener) } }
  publish(event: CommandEvent) { for (const listener of this.listeners) listener(Object.freeze({ ...event })) }
  clear() { this.listeners.clear() }
}
export const commandEventBus = new CommandEventBus()
