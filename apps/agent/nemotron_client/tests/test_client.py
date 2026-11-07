import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from nemotron_client import (
    LatencyLog,
    MalformedResponse,
    ModelResponse,
    ModelUnavailable,
    NemotronClient,
    NemotronConfig,
    ToolCall,
    ToolSpec,
)


def make_config(**kw):
    return NemotronConfig(model_id="nvidia/test-nemotron-70b",
                          endpoint="http://127.0.0.1:9/v1",
                          timeout_s=2.0, max_retries=1,
                          retry_backoff_s=0.01, **kw)


def ok_response(tool_calls=None, content="done"):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return json.dumps({
        "id": "chatcmpl-x", "model": "nvidia/test-nemotron-70b",
        "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }).encode()


def tc(name, args):
    return {"id": "call_1", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


def fake_transport(responses):
    """Queue of (status, body) or Exception to raise."""
    it = iter(responses)
    calls = []

    def transport(url, headers, body, timeout):
        calls.append({"url": url, "headers": headers, "body": body})
        item = next(it)
        if isinstance(item, Exception):
            raise item
        return item
    transport.calls = calls
    return transport


def test_chat_parses_tool_calls_and_logs_latency():
    log = LatencyLog()
    tr = fake_transport([(200, ok_response([tc("get_recent_observations",
                                             {"incident_id": "inc-1", "limit": 5})]))])
    c = NemotronClient(make_config(), transport=tr, logger=log)
    tools = [ToolSpec("get_recent_observations", "fetch obs",
                      {"type": "object", "properties": {}})]
    resp = c.chat([{"role": "user", "content": "investigate inc-1"}], tools)
    assert isinstance(resp, ModelResponse)
    assert len(resp.tool_calls) == 1
    call = resp.tool_calls[0]
    assert isinstance(call, ToolCall)
    assert call.name == "get_recent_observations"
    assert call.arguments == {"incident_id": "inc-1", "limit": 5}
    assert resp.usage["prompt_tokens"] == 10
    assert resp.latency_ms >= 0
    assert log.entries[0]["tool_calls"] == ["get_recent_observations"]
    assert log.entries[0]["model"] == "nvidia/test-nemotron-70b"
    # request envelope
    sent = json.loads(tr.calls[0]["body"])
    assert sent["model"] == "nvidia/test-nemotron-70b"
    assert sent["tools"][0]["function"]["name"] == "get_recent_observations"


def test_unparseable_tool_arguments_kept_raw():
    tr = fake_transport([(200, ok_response([
        {"id": "c", "type": "function",
         "function": {"name": "x", "arguments": "{not json"}}]))])
    c = NemotronClient(make_config(), transport=tr)
    resp = c.chat([{"role": "user", "content": "hi"}])
    assert resp.tool_calls[0].arguments == {"_unparseable": "{not json"}
    assert resp.tool_calls[0].raw_arguments == "{not json"


def test_retries_on_5xx_then_succeeds():
    tr = fake_transport([(503, b"busy"), (200, ok_response(content="ok"))])
    c = NemotronClient(make_config(), transport=tr)
    resp = c.chat([{"role": "user", "content": "hi"}])
    assert resp.content == "ok"
    assert len(tr.calls) == 2


def test_exhausts_retries_raises_unavailable():
    tr = fake_transport([(503, b""), (503, b"")])
    c = NemotronClient(make_config(), transport=tr)
    with pytest.raises(ModelUnavailable):
        c.chat([{"role": "user", "content": "hi"}])


def test_auth_failure_not_retried():
    tr = fake_transport([(401, b"unauthorized")])
    c = NemotronClient(make_config(), transport=tr)
    with pytest.raises(ModelUnavailable, match="auth"):
        c.chat([{"role": "user", "content": "hi"}])
    assert len(tr.calls) == 1


def test_malformed_envelope_rejected():
    tr = fake_transport([(200, b"not json at all")])
    c = NemotronClient(make_config(), transport=tr)
    with pytest.raises(MalformedResponse):
        c.chat([{"role": "user", "content": "hi"}])


def test_transport_exception_wrapped():
    tr = fake_transport([ModelUnavailable("down"), ModelUnavailable("down")])
    c = NemotronClient(make_config(), transport=tr)
    with pytest.raises(ModelUnavailable):
        c.chat([{"role": "user", "content": "hi"}])


def test_real_http_server_roundtrip():
    """Integration: real HTTP through urllib transport."""
    captured = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers["Content-Length"])
            captured["body"] = self.rfile.read(n)
            captured["auth"] = self.headers.get("Authorization")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(ok_response([tc("ping", {})]))

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    cfg = NemotronConfig(model_id="m", endpoint=f"http://127.0.0.1:{srv.server_port}/v1",
                         api_key_env="TEST_NVIDIA_KEY", timeout_s=5)
    import os
    os.environ["TEST_NVIDIA_KEY"] = "sekrit"
    c = NemotronClient(cfg)
    resp = c.chat([{"role": "user", "content": "x"}])
    srv.shutdown()
    assert resp.tool_calls[0].name == "ping"
    assert captured["auth"] == "Bearer sekrit"
    assert json.loads(captured["body"])["model"] == "m"
