"""Make sibling service packages importable without installing them.

Every apps/**/src directory is appended to sys.path so the facade can
reuse the existing service packages (identity, incident_records,
containment_policy, ...) exactly as their own pytest suites do.
"""
from __future__ import annotations

import sys
from pathlib import Path

# apps/api/src/sentinel_api/paths.py -> repo root is parents[4]
REPO_ROOT = Path(__file__).resolve().parents[4]


def ensure_service_paths() -> None:
    apps_dir = REPO_ROOT / "apps"
    if not apps_dir.is_dir():
        return
    for src in sorted(apps_dir.rglob("src")):
        if src.is_dir() and str(src) not in sys.path:
            sys.path.insert(0, str(src))


ensure_service_paths()
