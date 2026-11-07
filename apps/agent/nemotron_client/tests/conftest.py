import os

import pytest


@pytest.fixture(autouse=True)
def _fake_key():
    os.environ.setdefault("NVIDIA_API_KEY", "test-key-not-real")
    yield
