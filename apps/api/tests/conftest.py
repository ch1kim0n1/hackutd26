import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sentinel_api.app import create_app  # noqa: E402


@pytest.fixture()
def app():
    return create_app(seed=True)


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture()
def state(app):
    return app.state.svc


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def tokens(client, state):
    """Human login tokens + the seeded agent machine token."""
    out = {}
    for login_name, key in (("root-admin", "admin"), ("commander", "commander"),
                            ("responder", "responder"), ("observer", "observer")):
        r = client.post("/auth/login", json={"username": login_name})
        assert r.status_code == 200, r.text
        out[key] = r.json()["token"]
    out["agent"] = next(
        t for t, uid in state.identity.sessions.items()
        if state.identity.users[uid].role.value == "agent")
    return out


@pytest.fixture()
def auth(tokens):
    return {k: _auth(v) for k, v in tokens.items()}
