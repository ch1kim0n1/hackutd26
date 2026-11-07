"""Scripted model for tests — replays canned responses, self-contained
(no dependency on the nemotron_client package; same duck-typed shape)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str = ""


@dataclass
class FakeResponse:
    content: str = ""
    tool_calls: list[FakeToolCall] = field(default_factory=list)
    model: str = "scripted"
    latency_ms: float = 1.0


def tc(name: str, args: dict, call_id: str = "call_1") -> FakeToolCall:
    return FakeToolCall(id=call_id, name=name, arguments=args,
                        raw_arguments=json.dumps(args))


class ScriptedModel:
    """Returns queued FakeResponses; records every message list seen."""

    def __init__(self, responses: list[FakeResponse]):
        self.responses = list(responses)
        self.seen_messages: list[list[dict]] = []

    def chat(self, messages, tools=None, tool_choice="auto") -> FakeResponse:
        self.seen_messages.append([dict(m) for m in messages])
        if not self.responses:
            return FakeResponse(content="(script exhausted)")
        return self.responses.pop(0)
