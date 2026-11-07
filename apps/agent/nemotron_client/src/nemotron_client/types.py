"""Structured tool-call types. The model may ONLY emit these shapes;
argument validation happens downstream (docs/05 strict schemas)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolSpec:
    """One allowlisted tool exposed to the model."""
    name: str
    description: str
    parameters: dict[str, Any]          # JSON-schema-ish object
    strict: bool = True

    def to_openai_tool(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
                "strict": self.strict,
            },
        }


@dataclass
class ToolCall:
    """A model-requested tool invocation (untrusted until validated)."""
    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str = ""

    @classmethod
    def parse(cls, raw: dict) -> "ToolCall":
        fn = raw.get("function", {})
        args_raw = fn.get("arguments", "{}")
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw)
        except json.JSONDecodeError:
            args = {"_unparseable": args_raw}
        return cls(id=str(raw.get("id", "")), name=str(fn.get("name", "")),
                   arguments=args if isinstance(args, dict) else {},
                   raw_arguments=args_raw if isinstance(args_raw, str) else json.dumps(args_raw))


@dataclass
class ModelResponse:
    """One chat completion: text + tool calls + usage/latency provenance."""
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    usage: dict = field(default_factory=dict)
    latency_ms: float = 0.0
    raw: dict = field(default_factory=dict)


class ModelUnavailable(RuntimeError):
    """Endpoint unreachable / auth failed / timeout — degrade gracefully."""


class MalformedResponse(RuntimeError):
    """HTTP 200 but body violates the chat-completions envelope."""
