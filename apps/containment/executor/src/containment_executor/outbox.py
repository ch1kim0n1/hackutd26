"""Outbox — durable handoff from approval (#33) to executor.

Actions arrive ONLY via approved OutboxItems; delivery is idempotent by
action_id (re-delivery is a no-op, docs/08 threat 7). Expired items are
dropped. The executor trusts nothing else — no direct action intake."""
from __future__ import annotations

import time
from typing import Callable

from .models import ExecState, ExecutionRecord, OutboxItem


class Outbox:
    def __init__(self, clock: Callable[[], float] = time.time):
        self.clock = clock
        self.items: dict[str, OutboxItem] = {}
        self.records: dict[str, ExecutionRecord] = {}

    def deliver(self, item: OutboxItem) -> ExecutionRecord:
        """Idempotent: same action_id returns existing record, no re-queue."""
        if item.action_id in self.records:
            rec = self.records[item.action_id]
            # redelivery while still queued: return record unchanged —
            # do NOT clobber QUEUED state or it'd never execute
            if rec.state != ExecState.QUEUED:
                rec.transition(ExecState.SKIPPED_DUPLICATE,
                               reason="redelivery ignored")
            return rec
        if item.expires_at and item.expires_at < self.clock():
            rec = item.new_record()
            rec.transition(ExecState.REJECTED_UNAPPROVED,
                           reason="approval expired before execution")
            self.records[item.action_id] = rec
            return rec
        self.items[item.action_id] = item
        rec = item.new_record()
        self.records[item.action_id] = rec
        return rec

    def pending(self) -> list[OutboxItem]:
        now = self.clock()
        return [i for i in self.items.values()
                if i.expires_at >= now
                and self.records[i.action_id].state == ExecState.QUEUED]

    def complete(self, action_id: str) -> None:
        self.items.pop(action_id, None)
