"""Pinned Nemotron endpoint configuration (docs/05).

Model/endpoint are pinned in deployment config — never 'latest'.
Secrets arrive via env vars, never committed."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class NemotronConfig:
    """Exact pinned inference target. Change = new reviewed config."""
    model_id: str                 # e.g. "nvidia/llama-3.1-nemotron-70b-instruct"
    endpoint: str                 # base URL, e.g. "https://integrate.api.nvidia.com/v1"
    api_key_env: str = "NVIDIA_API_KEY"
    timeout_s: float = 30.0
    max_retries: int = 2
    retry_backoff_s: float = 0.5
    max_tokens: int = 2048
    temperature: float = 0.2
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls, **overrides) -> "NemotronConfig":
        """Build from env: NEMOTRON_MODEL_ID / NEMOTRON_ENDPOINT required."""
        model = os.environ.get("NEMOTRON_MODEL_ID", "")
        endpoint = os.environ.get("NEMOTRON_ENDPOINT", "")
        if not model or not endpoint:
            raise RuntimeError(
                "NEMOTRON_MODEL_ID and NEMOTRON_ENDPOINT must be set — "
                "no default model is assumed (docs/05 pin requirement)")
        return cls(model_id=model, endpoint=endpoint.rstrip("/"), **overrides)

    def api_key(self) -> str:
        key = os.environ.get(self.api_key_env, "")
        if not key:
            raise RuntimeError(f"{self.api_key_env} not set")
        return key
