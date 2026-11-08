"""Provider transport tests — issue #111.

Covers: env-driven live/fake selection, secret safety, the
NemotronChatModel adapter, deterministic fake, structured-assessment
validation, and a full InvestigationAgent run over a real local HTTP
server (urllib transport, OpenAI envelope, tool calls, latency log).
"""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

# sibling agent packages + this package's src (same trick the api
# facade uses; harmless when PYTHONPATH=src is already set)
_AGENT = Path(__file__).resolve().parents[2]          # apps/agent
for pkg in ("investigator", "hardening"):
    p = str(_AGENT / pkg / "src")
    if p not in sys.path:
        sys.path.insert(0, p)
_OWN = str(Path(__file__).resolve().parents[1] / "src")
if _OWN not in sys.path:
    sys.path.insert(0, _OWN)

from nemotron_client import (  # noqa: E402
    FakeNemotronModel,
    ModelResponse,
    NemotronChatModel,
    ToolCall,
    build_chat_model,
    validate_assessment,
)
from nemotron_client.provider import (  # noqa: E402
    ENDPOINT_ENV, KEY_ENV_NAME_ENV, MODEL_ID_ENV, MODE_ENV,
)
from investigator import (  # noqa: E402
    FakeBackends, InvestigationAgent, ToolContext, ToolRegistry,
)
from agent_safety import HardenedAgent, ModelOutputGuard, ToolGuard  # noqa: E402

SECRET_KEY = "nvapi-TEST-SECRET-DO-NOT-LOG-123"


def live_env(**over):
    env = {
        MODEL_ID_ENV: "nvidia/test-nemotron-70b",
        ENDPOINT_ENV: "http://127.0.0.1:9/v1",
        "NEMOTRON_API_KEY": SECRET_KEY,
    }
    env.update(over)
    return env


def live_env_at(url, **over):
    """live_env with the endpoint pointed at a local test server."""
    return live_env(**{ENDPOINT_ENV: url}, **over)


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

def test_auto_fake_when_unconfigured():
    model, info = build_chat_model(env={})
    assert info.mode == "fake"
    assert isinstance(model, FakeNemotronModel)
    assert "missing" in info.reason
    assert info.api_key_env == ""


def test_auto_fake_when_only_partial_config():
    for env in (
        {MODEL_ID_ENV: "m"},                                   # no endpoint/key
        {ENDPOINT_ENV: "http://x", "NEMOTRON_API_KEY": "k"},   # no model
        {MODEL_ID_ENV: "m", ENDPOINT_ENV: "http://x"},         # no key
    ):
        model, info = build_chat_model(env=env)
        assert info.mode == "fake", env
        assert isinstance(model, FakeNemotronModel)


def test_auto_live_when_fully_configured():
    model, info = build_chat_model(env=live_env())
    assert info.mode == "live"
    assert isinstance(model, NemotronChatModel)
    assert info.model_id == "nvidia/test-nemotron-70b"
    assert info.api_key_env == "NEMOTRON_API_KEY"
    # never any key material in the info object
    assert SECRET_KEY not in repr(info)


def test_explicit_live_missing_config_raises():
    with pytest.raises(RuntimeError, match="incomplete"):
        build_chat_model(env={MODE_ENV: "live", MODEL_ID_ENV: "m"})


def test_explicit_fake_ignores_live_config():
    sentinel = object()
    model, info = build_chat_model(env=live_env(SENTINEL_AGENT_MODEL="fake"),
                                   fallback=sentinel)
    assert model is sentinel and info.mode == "fake"


def test_invalid_mode_rejected():
    with pytest.raises(RuntimeError, match="invalid"):
        build_chat_model(env={MODE_ENV: "bogus"})


def test_key_env_resolution_order():
    # NEMOTRON_API_KEY preferred
    _, info = build_chat_model(env=live_env(NVIDIA_API_KEY="other"))
    assert info.api_key_env == "NEMOTRON_API_KEY"
    # NVIDIA_API_KEY fallback
    env = live_env()
    del env["NEMOTRON_API_KEY"]
    env["NVIDIA_API_KEY"] = SECRET_KEY
    _, info = build_chat_model(env=env)
    assert info.api_key_env == "NVIDIA_API_KEY"
    # NEMOTRON_API_KEY_ENV names a custom var
    env = live_env()
    del env["NEMOTRON_API_KEY"]
    env["MY_PROVIDER_KEY"] = SECRET_KEY
    env[KEY_ENV_NAME_ENV] = "MY_PROVIDER_KEY"
    _, info = build_chat_model(env=env)
    assert info.api_key_env == "MY_PROVIDER_KEY"
    # custom name set but var empty -> treated as missing
    env["MY_PROVIDER_KEY"] = ""
    _, info = build_chat_model(env=env)
    assert info.mode == "fake"


def test_no_secret_anywhere_in_outputs():
    """Key value must never appear in ProviderInfo, latency log, or errors."""
    model, info = build_chat_model(env=live_env())
    assert SECRET_KEY not in repr(info)
    tr_calls = []

    def tr(url, headers, body, timeout):
        tr_calls.append((url, headers, body))
        return 200, _ok_response([])

    model2, _ = build_chat_model(env=live_env(), transport=tr)
    model2.chat([{"role": "user", "content": "hi"}])
    # key IS sent as bearer header (that's its job) but nowhere else
    assert tr_calls[0][1]["Authorization"] == f"Bearer {SECRET_KEY}"
    assert SECRET_KEY not in tr_calls[0][0]
    assert SECRET_KEY not in tr_calls[0][2].decode()
    assert SECRET_KEY not in repr(model2.client.log.entries)
    assert SECRET_KEY not in repr(info)


# ---------------------------------------------------------------------------
# Adapter: dict specs -> ToolSpec -> OpenAI payload
# ---------------------------------------------------------------------------

def _dict_specs():
    return [{"type": "function", "function": {
        "name": "get_recent_observations",
        "description": "fetch obs",
        "parameters": {"type": "object",
                       "properties": {"incident_id": {"type": "string"}},
                       "required": ["incident_id"]},
        "strict": True}}]


def test_adapter_converts_dict_tool_specs():
    seen = {}

    def tr(url, headers, body, timeout):
        seen["payload"] = json.loads(body)
        return 200, _ok_response([])

    model, _ = build_chat_model(env=live_env(), transport=tr)
    model.chat([{"role": "user", "content": "hi"}], tools=_dict_specs())
    tool = seen["payload"]["tools"][0]
    assert tool["type"] == "function"
    assert tool["function"]["name"] == "get_recent_observations"
    assert tool["function"]["strict"] is True
    assert tool["function"]["parameters"]["required"] == ["incident_id"]


def test_adapter_accepts_toolspec_passthrough():
    from nemotron_client import ToolSpec
    from nemotron_client.provider import _to_tool_spec
    spec = ToolSpec("x", "d", {"type": "object"})
    assert _to_tool_spec(spec) is spec
    assert _to_tool_spec(_dict_specs()[0]).name == "get_recent_observations"


# ---------------------------------------------------------------------------
# FakeNemotronModel
# ---------------------------------------------------------------------------

def _mr(content="", calls=None):
    return ModelResponse(
        content=content,
        tool_calls=[ToolCall(id=f"c{i}", name=n,
                             arguments=a, raw_arguments=json.dumps(a))
                    for i, (n, a) in enumerate(calls or [])],
        model="fake-nemotron", latency_ms=0.5)


def test_fake_model_replays_and_rewinds_per_run():
    script = [_mr("one"), _mr("two")]
    m = FakeNemotronModel(script)
    msgs1 = [{"role": "system", "content": "s"},
             {"role": "user", "content": "investigate"}]
    assert m.chat(msgs1).content == "one"
    # same run continues (messages grew -> no rewind)
    msgs1.append({"role": "assistant", "content": "x"})
    assert m.chat(msgs1).content == "two"
    # exhausted -> deterministic tail
    assert "exhausted" in m.chat(msgs1).content
    # NEW run rewinds
    msgs2 = [{"role": "system", "content": "s"},
             {"role": "user", "content": "investigate inc-2"}]
    assert m.chat(msgs2).content == "one"


# ---------------------------------------------------------------------------
# validate_assessment
# ---------------------------------------------------------------------------

def test_validate_assessment_accepts_real_assessment():
    from dataclasses import asdict
    from investigator.agent import Assessment
    a = Assessment(hypotheses=["h1"], competing_explanations=["c"],
                   unknowns=["u"], evidence_ids=["ev-1"], summary="s")
    assert validate_assessment(asdict(a)) == []


def test_validate_assessment_flags_violations():
    assert validate_assessment("nope") == ["assessment is not an object"]
    v = validate_assessment({"hypotheses": "x", "summary": 3})
    assert any("hypotheses" in x for x in v)
    assert any("summary" in x for x in v)
    assert any("missing" in x for x in v)
    v = validate_assessment({"hypotheses": [], "competing_explanations": [],
                             "unknowns": [], "evidence_ids": [1],
                             "summary": "s"})
    assert any("evidence_ids[0]" in x for x in v)


# ---------------------------------------------------------------------------
# End-to-end: real urllib -> local HTTP server -> InvestigationAgent
# ---------------------------------------------------------------------------

def _ok_response(tool_calls=None, content="done", model="m"):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return json.dumps({
        "id": "chatcmpl-x", "model": model,
        "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }).encode()


def _tc(name, args, i=0):
    return {"id": f"call_{i}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


class _ScriptedHTTP:
    """Local OpenAI-compatible server replaying canned responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers["Content-Length"])
                body = self.rfile.read(n)
                outer.requests.append({
                    "path": self.path,
                    "auth": self.headers.get("Authorization"),
                    "body": json.loads(body)})
                item = outer.responses.pop(0) if outer.responses else \
                    (200, _ok_response(content="(script exhausted)"))
                status, payload = item if isinstance(item, tuple) else \
                    (200, item)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), H)
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"

    def close(self):
        self.server.shutdown()


CTX = ToolContext(incident_id="inc-1",
                  allowed_zones={"rack-01"},
                  allowed_waypoints={"wp-rack-01"},
                  allowed_devices={"puck-a-01", "rover-01"})


def _agent(model):
    be = FakeBackends()
    reg = ToolRegistry(CTX, be.as_backends())
    return InvestigationAgent(model, reg), be


def test_live_transport_full_investigation():
    """Real inference path: env config -> NemotronClient -> urllib ->
    local OpenAI server -> tool calls -> validated Assessment."""
    http = _ScriptedHTTP([
        (200, _ok_response([_tc("get_recent_observations",
                                {"incident_id": "inc-1", "limit": 5}, 0),
                            _tc("get_authorized_assets",
                                {"zone_id": "rack-01"}, 1)])),
        (200, _ok_response([_tc("append_agent_assessment",
                                {"incident_id": "inc-1",
                                 "assessment": "Unknown device observed; "
                                               "consistent with rogue test "
                                               "or misconfiguration — not "
                                               "confirmed exfiltration.",
                                 "evidence_ids": ["obs-1", "obs-2"],
                                 "unknowns": ["device owner", "dwell time"]},
                                2)])),
        (200, _ok_response(content="Assessment appended.")),
    ])
    try:
        env = live_env_at(http.url)
        model, info = build_chat_model(env=env)   # real urllib transport
        assert info.mode == "live"
        agent, be = _agent(model)
        out = agent.investigate("unknown BLE device near rack-01")

        assert not out.degraded
        assert out.tool_calls_made == 3
        assert len(be.assessments) == 1
        assert be.assessments[0]["evidence_ids"] == ["obs-1", "obs-2"]
        assert validate_assessment(
            {"hypotheses": out.hypotheses or ["x"],
             "competing_explanations": out.competing_explanations,
             "unknowns": out.unknowns,
             "evidence_ids": out.evidence_ids,
             "summary": out.summary}) == []
        # wire-level proof: bearer auth + tools array + model pin sent
        assert all(r["auth"] == f"Bearer {SECRET_KEY}" for r in http.requests)
        assert http.requests[0]["body"]["model"] == "nvidia/test-nemotron-70b"
        assert http.requests[0]["body"]["tools"]
        # latency provenance flowed through (model entries in the trace)
        model_entries = [t for t in out.trace if "latency_ms" in t]
        assert model_entries and all("model" in t for t in model_entries)
    finally:
        http.close()


def test_malformed_response_degrades_gracefully():
    """N04/N05: garbage HTTP 200 body -> MalformedResponse -> degraded
    assessment, no crash, manual path unaffected."""
    http = _ScriptedHTTP([(200, b"this is not json")])
    try:
        model, _ = build_chat_model(env=live_env_at(http.url),
                                    transport=None)
        agent, be = _agent(model)
        out = agent.investigate("test")
        assert out.degraded
        assert be.missions == [] and be.assessments == []
    finally:
        http.close()


def test_api_5xx_retries_then_degrades():
    http = _ScriptedHTTP([(503, b"busy"), (503, b"busy"), (503, b"busy")])
    try:
        env = live_env_at(http.url,
                          NEMOTRON_MAX_RETRIES="1", NEMOTRON_TIMEOUT_S="2")
        model, _ = build_chat_model(env=env)
        agent, _ = _agent(model)
        out = agent.investigate("test")
        assert out.degraded
        # retries honored: max_retries=1 -> 2 attempts total
        assert len(http.requests) == 2
    finally:
        http.close()


def test_auth_failure_single_attempt_no_retry():
    http = _ScriptedHTTP([(401, b"unauthorized")])
    try:
        model, _ = build_chat_model(env=live_env_at(http.url))
        agent, _ = _agent(model)
        out = agent.investigate("test")
        assert out.degraded
        assert len(http.requests) == 1   # auth failure is not retried
    finally:
        http.close()


def test_unreachable_endpoint_degrades():
    env = live_env_at("http://127.0.0.1:1/v1",
                      NEMOTRON_TIMEOUT_S="0.2", NEMOTRON_MAX_RETRIES="0")
    model, _ = build_chat_model(env=env)
    agent, _ = _agent(model)
    out = agent.investigate("test")
    assert out.degraded


# ---------------------------------------------------------------------------
# Authority boundary: model output can never reach actuators
# ---------------------------------------------------------------------------

def test_model_cannot_escape_tool_allowlist():
    """Even a hostile model response naming authority tools is denied —
    registry allowlist + ToolGuard both hold end-to-end over live transport."""
    http = _ScriptedHTTP([
        (200, _ok_response([
            _tc("run_shell_command", {"cmd": "rm -rf /"}, 0),
            _tc("approve_containment", {"proposal_id": "p1"}, 1),
            _tc("execute_containment", {}, 2),
            _tc("get_rover_status", {"device_id": "rover-01"}, 3),
        ])),
        (200, _ok_response(content="done")),
    ])
    try:
        model, _ = build_chat_model(env=live_env_at(http.url))
        be = FakeBackends()
        reg = ToolRegistry(CTX, be.as_backends())
        guard = ToolGuard({s["name"] for s in reg.specs()})
        og = ModelOutputGuard()
        agent = HardenedAgent(InvestigationAgent(model, reg), guard, og)
        result = agent.investigate("test")
        # hostile calls denied before reaching backends
        denied_names = {d["tool"] for d in result.denied_tool_calls}
        assert {"run_shell_command", "approve_containment",
                "execute_containment"} <= denied_names
        # only the allowlisted read tool reached a backend
        assert be.calls.get("get_rover_status") or \
            any(c["tool"] == "get_rover_status" and c.get("ok")
                for c in reg.calls)
    finally:
        http.close()


def test_assessment_output_guard_rejects_fabricated_citations():
    http = _ScriptedHTTP([
        (200, _ok_response([
            _tc("append_agent_assessment",
                {"incident_id": "inc-1",
                 "assessment": "Containment has been approved and executed.",
                 "evidence_ids": ["ev-FABRICATED-999"],
                 "unknowns": []}, 0),
        ])),
        (200, _ok_response(content="done")),
    ])
    try:
        model, _ = build_chat_model(env=live_env_at(http.url))
        be = FakeBackends()
        reg = ToolRegistry(CTX, be.as_backends())
        guard = ToolGuard({s["name"] for s in reg.specs()})
        og = ModelOutputGuard(known_evidence_ids={"obs-1", "ev-1"})
        agent = HardenedAgent(InvestigationAgent(model, reg), guard, og)
        result = agent.investigate("test")
        assert result.assessment_violations
        assert not result.assessment_accepted
        # fabricated assessment never recorded
        assert be.assessments == []
    finally:
        http.close()
