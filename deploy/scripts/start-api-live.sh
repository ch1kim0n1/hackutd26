#!/usr/bin/env bash
# Start the Sentinel API with live NVIDIA Nemotron inference.
#
# Prereqs (export in THIS shell first — the key is never written to disk
# by this script):
#   NVIDIA_API_KEY=nvapi-...        # or NEMOTRON_API_KEY
#
# Optional overrides:
#   NEMOTRON_ENDPOINT   (default below)
#   NEMOTRON_MODEL_ID   (default below)
#   SENTINEL_AGENT_TOKEN, SENTINEL_ROVER_EVIDENCE_DIR, API port via env
#
# The provider reads the key lazily from the process environment at request
# time; it is never logged, committed, or echoed by this script.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT/apps/api"

export SENTINEL_AGENT_MODEL="${SENTINEL_AGENT_MODEL:-live}"
export NEMOTRON_ENDPOINT="${NEMOTRON_ENDPOINT:-https://integrate.api.nvidia.com/v1/chat/completions}"
export NEMOTRON_MODEL_ID="${NEMOTRON_MODEL_ID:-nvidia/nemotron-3.5-lightning-30b-a3b}"
export SENTINEL_AGENT_TOKEN="${SENTINEL_AGENT_TOKEN:?set SENTINEL_AGENT_TOKEN}"
export SENTINEL_ROVER_EVIDENCE_DIR="${SENTINEL_ROVER_EVIDENCE_DIR:-}"

# Fail fast if no key env var is present (names only — never values).
if [ -z "${NEMOTRON_API_KEY:-}" ] && [ -z "${NVIDIA_API_KEY:-}" ]; then
  echo "error: set NVIDIA_API_KEY or NEMOTRON_API_KEY in this shell first" >&2
  exit 1
fi

exec env PYTHONPATH=src python3 -m uvicorn sentinel_api.app:app --port "${API_PORT:-8000}"
