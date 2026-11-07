"""Nemotron chat-completions client with tool calling (docs/05).

Stdlib-only transport (urllib) so the worker has no heavy deps.
Every call logs model id, latency_ms, tool names + arg keys — the
decision trace required by docs/05 reliability + docs/08 audit."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Callable

from .config import NemotronConfig
from .types import (
    MalformedResponse,
    ModelResponse,
    ModelUnavailable,
    ToolCall,
    ToolSpec,
)

Transport = Callable[[str, dict, dict, float], tuple[int, bytes]]


def _urllib_transport(url: str, headers: dict, body: bytes,
                      timeout_s: float) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ModelUnavailable(f"endpoint unreachable: {e}") from e


class LatencyLog:
    """Append-only in-memory call log; ship to audit downstream."""

    def __init__(self):
        self.entries: list[dict] = []

    def record(self, **kw) -> None:
        self.entries.append(kw)


class NemotronClient:
    def __init__(self, config: NemotronConfig,
                 transport: Transport | None = None,
                 logger: LatencyLog | None = None):
        self.config = config
        self.transport = transport or _urllib_transport
        self.log = logger or LatencyLog()

    # ---------------- public API ----------------
    def chat(self, messages: list[dict],
             tools: list[ToolSpec] | None = None,
             tool_choice: str = "auto") -> ModelResponse:
        """One chat completion. Raises ModelUnavailable / MalformedResponse."""
        payload = {
            "model": self.config.model_id,
            "messages": messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }
        if tools:
            payload["tools"] = [t.to_openai_tool() for t in tools]
            payload["tool_choice"] = tool_choice
        body = json.dumps(payload).encode()
        headers = {
            "Authorization": f"Bearer {self.config.api_key()}",
            "Content-Type": "application/json",
        }
        url = f"{self.config.endpoint}/chat/completions"

        last_err: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            t0 = time.monotonic()
            try:
                status, raw = self.transport(url, headers, body,
                                             self.config.timeout_s)
            except ModelUnavailable as e:
                last_err = e
                self._sleep(attempt)
                continue
            latency_ms = (time.monotonic() - t0) * 1000.0
            if status in (401, 403):
                raise ModelUnavailable(f"auth rejected: HTTP {status}")
            if status == 429 or status >= 500:
                last_err = ModelUnavailable(f"HTTP {status}")
                self._sleep(attempt)
                continue
            if status != 200:
                raise MalformedResponse(f"unexpected HTTP {status}")
            try:
                resp = self._parse(raw)
            except MalformedResponse:
                raise
            resp.latency_ms = latency_ms
            self.log.record(
                model=self.config.model_id, latency_ms=round(latency_ms, 1),
                tool_calls=[tc.name for tc in resp.tool_calls],
                attempt=attempt,
            )
            return resp
        raise ModelUnavailable(f"exhausted retries: {last_err}")

    # ---------------- internals ----------------
    def _sleep(self, attempt: int) -> None:
        import time as _t
        _t.sleep(self.config.retry_backoff_s * (attempt + 1))

    def _parse(self, raw: bytes) -> ModelResponse:
        try:
            data = json.loads(raw)
            choice = data["choices"][0]["message"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
            raise MalformedResponse(f"bad envelope: {e}") from e
        calls = [ToolCall.parse(tc) for tc in choice.get("tool_calls", [])]
        return ModelResponse(
            content=choice.get("content") or "",
            tool_calls=calls,
            model=str(data.get("model", "")),
            usage=data.get("usage", {}) if isinstance(data.get("usage"), dict) else {},
            raw=data,
        )
