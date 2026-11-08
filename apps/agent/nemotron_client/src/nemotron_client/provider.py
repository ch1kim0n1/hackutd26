"""Provider transport — wires NemotronClient into the ChatModel contract
used by investigator.InvestigationAgent, with env-driven live/fake
selection and secret-safe configuration (issue #111, docs/05).

Environment variables (names documented; VALUES are never logged,
committed, or placed in ProviderInfo):

  NEMOTRON_MODEL_ID      pinned model id — REQUIRED for live mode
  NEMOTRON_ENDPOINT      base URL e.g. https://integrate.api.nvidia.com/v1
                         — REQUIRED for live mode
  NEMOTRON_API_KEY       preferred API-key env var (issue #111 name)
  NVIDIA_API_KEY         provider-required fallback key env var
  NEMOTRON_API_KEY_ENV   optional: name of a DIFFERENT env var that holds
                         the key (takes precedence over the two above)
  SENTINEL_AGENT_MODEL   auto | live | fake   (default: auto)
  NEMOTRON_TIMEOUT_S     optional float override (default 30.0)
  NEMOTRON_MAX_RETRIES   optional int override   (default 2)
  NEMOTRON_MAX_TOKENS    optional int override   (default 2048)
  NEMOTRON_TEMPERATURE   optional float override (default 0.2)

Mode resolution (auto): live only when model id + endpoint + a key env var
are ALL present; otherwise fake. Explicit live with incomplete config
raises — a half-configured deployment must fail loudly, not silently
degrade. The fake path is deterministic and makes no network calls.
"""
from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Optional

from .client import NemotronClient
from .config import NemotronConfig
from .types import ModelResponse, ToolSpec

# Env names — the ONLY credential-related strings this module ever handles.
MODEL_ID_ENV = "NEMOTRON_MODEL_ID"
ENDPOINT_ENV = "NEMOTRON_ENDPOINT"
KEY_ENV_NAMES = ("NEMOTRON_API_KEY", "NVIDIA_API_KEY")
KEY_ENV_NAME_ENV = "NEMOTRON_API_KEY_ENV"   # names the env var holding the key
MODE_ENV = "SENTINEL_AGENT_MODEL"

_MODE_LIVE = "live"
_MODE_FAKE = "fake"


@dataclass(frozen=True)
class ProviderInfo:
    """Non-secret description of the selected provider. Contains env var
    NAMES and config values only — never key material."""
    mode: str                     # "live" | "fake"
    model_id: str = ""
    endpoint: str = ""
    api_key_env: str = ""         # name of the env var, not its value
    reason: str = ""


# ---------------------------------------------------------------------------
# ChatModel adapter — investigator dict-shaped specs -> NemotronClient ToolSpec
# ---------------------------------------------------------------------------

def _to_tool_spec(t: Any) -> ToolSpec:
    """Accept ToolSpec (passthrough) or the OpenAI dict shape the
    investigator's ChatModel protocol emits:
    {"type":"function","function":{"name","description","parameters","strict"}}"""
    if isinstance(t, ToolSpec):
        return t
    if isinstance(t, dict):
        fn = t.get("function", t)
        return ToolSpec(
            name=str(fn.get("name", "")),
            description=str(fn.get("description", "")),
            parameters=fn.get("parameters") or {"type": "object"},
            strict=bool(fn.get("strict", True)),
        )
    raise TypeError(f"unsupported tool spec shape: {type(t).__name__}")


class NemotronChatModel:
    """ChatModel-protocol adapter over NemotronClient.

    investigator.InvestigationAgent calls chat(messages, tools, tool_choice)
    with OpenAI-shaped dict tool specs; NemotronClient wants ToolSpec
    objects. This adapter bridges them and returns ModelResponse unchanged
    (content/tool_calls/latency_ms/model are already duck-compatible).
    """

    def __init__(self, client: NemotronClient):
        self.client = client

    @property
    def log(self):
        return self.client.log

    def chat(self, messages: list[dict], tools: Optional[list] = None,
             tool_choice: str = "auto") -> ModelResponse:
        specs = [_to_tool_spec(t) for t in (tools or [])]
        return self.client.chat(
            messages, tools=specs or None, tool_choice=tool_choice)


# ---------------------------------------------------------------------------
# Deterministic fake — same ChatModel duck-type, zero network
# ---------------------------------------------------------------------------

class FakeNemotronModel:
    """Replays a script of ModelResponse objects for CI/dev.

    A fresh investigation (messages == [system, user]) rewinds the script
    cursor, so one instance serves repeated runs deterministically.
    """

    def __init__(self, script: Sequence[ModelResponse] = (),
                 model_id: str = "fake-nemotron"):
        self.script = list(script)
        self.model_id = model_id
        self._i = 0
        self.seen_messages: list[list[dict]] = []

    @staticmethod
    def _is_new_run(messages: list[dict]) -> bool:
        return (len(messages) <= 2
                and messages
                and messages[0].get("role") == "system")

    def chat(self, messages: list[dict], tools: Optional[list] = None,
             tool_choice: str = "auto") -> ModelResponse:
        self.seen_messages.append([dict(m) for m in messages])
        if self._is_new_run(messages):
            self._i = 0
        if self._i < len(self.script):
            resp = self.script[self._i]
            self._i += 1
        else:
            resp = ModelResponse(
                content="(fake nemotron: script exhausted)",
                model=self.model_id, latency_ms=0.1)
        if not isinstance(resp, ModelResponse):
            resp = ModelResponse(
                content=getattr(resp, "content", "") or "",
                tool_calls=[tc for tc in getattr(resp, "tool_calls", [])],
                model=getattr(resp, "model", "") or self.model_id,
                latency_ms=float(getattr(resp, "latency_ms", 0.0) or 0.0))
        return resp


# ---------------------------------------------------------------------------
# Env-driven factory
# ---------------------------------------------------------------------------

def _env_str(env: Mapping, name: str) -> str:
    return str(env.get(name, "") or "").strip()


def _env_float(env: Mapping, name: str, default: float) -> float:
    raw = _env_str(env, name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise RuntimeError(f"{name}={raw!r} is not a number")


def _env_int(env: Mapping, name: str, default: int) -> int:
    raw = _env_str(env, name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"{name}={raw!r} is not an integer")


def _resolve_api_key_env(env: Mapping) -> Optional[str]:
    """Return the NAME of the env var holding the API key, or None.
    Checks NEMOTRON_API_KEY_ENV first (explicit operator choice), then
    NEMOTRON_API_KEY, then the provider-required NVIDIA_API_KEY. The value
    itself is never read here — NemotronConfig.api_key() reads it lazily
    at request time."""
    explicit = _env_str(env, KEY_ENV_NAME_ENV)
    if explicit:
        return explicit if _env_str(env, explicit) else None
    for name in KEY_ENV_NAMES:
        if _env_str(env, name):
            return name
    return None


def _missing_live_config(env: Mapping) -> list[str]:
    missing = []
    if not _env_str(env, MODEL_ID_ENV):
        missing.append(MODEL_ID_ENV)
    if not _env_str(env, ENDPOINT_ENV):
        missing.append(ENDPOINT_ENV)
    if _resolve_api_key_env(env) is None:
        missing.append("api key env (" + "|".join(KEY_ENV_NAMES) + ")")
    return missing


def build_chat_model(env: Optional[Mapping] = None, *,
                     transport=None,
                     fallback=None,
                     scripted: Sequence[ModelResponse] = ()
                     ) -> tuple[Any, ProviderInfo]:
    """Select the investigation ChatModel from environment configuration.

    Returns (model, ProviderInfo). ``fallback`` is any ChatModel used for
    fake mode (e.g. investigator.ScriptedModel for the API facade's canned
    demo investigation); when absent, FakeNemotronModel replays ``scripted``.

    ``transport`` is injected into NemotronClient for tests — it replaces
    urllib entirely, so no real network call is possible through it.
    """
    env = os.environ if env is None else env
    mode_req = _env_str(env, MODE_ENV).lower() or "auto"
    if mode_req not in ("auto", _MODE_LIVE, _MODE_FAKE):
        raise RuntimeError(
            f"{MODE_ENV}={mode_req!r} invalid — expected auto|live|fake")

    missing = _missing_live_config(env)

    if mode_req == _MODE_FAKE or (mode_req == "auto" and missing):
        reason = (f"{MODE_ENV}={mode_req}" if mode_req == _MODE_FAKE
                  else "auto: missing " + ", ".join(missing))
        model = fallback if fallback is not None else FakeNemotronModel(scripted)
        return model, ProviderInfo(mode=_MODE_FAKE, reason=reason)

    if missing:
        raise RuntimeError(
            f"{MODE_ENV}=live but config incomplete: missing "
            + ", ".join(missing))

    key_env = _resolve_api_key_env(env)
    cfg = NemotronConfig(
        model_id=_env_str(env, MODEL_ID_ENV),
        endpoint=_env_str(env, ENDPOINT_ENV).rstrip("/"),
        api_key_env=key_env,
        timeout_s=_env_float(env, "NEMOTRON_TIMEOUT_S", 30.0),
        max_retries=_env_int(env, "NEMOTRON_MAX_RETRIES", 2),
        max_tokens=_env_int(env, "NEMOTRON_MAX_TOKENS", 2048),
        temperature=_env_float(env, "NEMOTRON_TEMPERATURE", 0.2),
        environ=env,   # same mapping used for selection — key read stays consistent
    )
    client = NemotronClient(cfg, transport=transport)
    return NemotronChatModel(client), ProviderInfo(
        mode=_MODE_LIVE, model_id=cfg.model_id, endpoint=cfg.endpoint,
        api_key_env=key_env)


# ---------------------------------------------------------------------------
# Structured assessment validation (transport-side result contract)
# ---------------------------------------------------------------------------

ASSESSMENT_LIST_FIELDS = ("hypotheses", "competing_explanations",
                          "unknowns", "evidence_ids")


def validate_assessment(d: Any) -> list[str]:
    """Schema-check a serialized investigator Assessment (the structured
    result the transport produces). Returns violation strings; [] = valid.
    This validates SHAPE only — content authority is ModelOutputGuard's job.
    """
    violations: list[str] = []
    if not isinstance(d, dict):
        return ["assessment is not an object"]
    for k in ASSESSMENT_LIST_FIELDS:
        if k not in d:
            violations.append(f"missing '{k}'")
        elif not isinstance(d[k], list):
            violations.append(f"'{k}' must be a list")
    if "summary" not in d:
        violations.append("missing 'summary'")
    elif not isinstance(d["summary"], str):
        violations.append("'summary' must be a string")
    ev = d.get("evidence_ids")
    if isinstance(ev, list):
        for i, x in enumerate(ev):
            if not isinstance(x, str):
                violations.append(f"evidence_ids[{i}] must be a string")
                break
    hy = d.get("hypotheses")
    if isinstance(hy, list):
        for i, x in enumerate(hy):
            if not isinstance(x, str):
                violations.append(f"hypotheses[{i}] must be a string")
                break
    if "degraded" in d and not isinstance(d["degraded"], bool):
        violations.append("'degraded' must be a boolean")
    return violations


__all__ = [
    "ASSESSMENT_LIST_FIELDS",
    "FakeNemotronModel",
    "KEY_ENV_NAME_ENV",
    "KEY_ENV_NAMES",
    "MODE_ENV",
    "MODEL_ID_ENV",
    "ENDPOINT_ENV",
    "NemotronChatModel",
    "ProviderInfo",
    "build_chat_model",
    "validate_assessment",
]
