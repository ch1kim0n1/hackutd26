#!/usr/bin/env python3
"""Safe reset for virtual data-center services (#101).

Restarts the compose stack from a clean state. Synthetic data only —
nothing persistent to lose. Usage:
  python3 apps/datacenter/scripts/reset.py [--down] [--build]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.dc.yml"


def run(*args: str) -> int:
    print("+", " ".join(args), flush=True)
    return subprocess.call(args)


def main() -> int:
    down = "--down" in sys.argv
    build = "--build" in sys.argv
    base = ["docker", "compose", "-f", str(COMPOSE)]
    if down:
        return run(*base, "down", "-v")
    rc = run(*base, "up", "-d", *( ["--build"] if build else [] ))
    if rc == 0:
        print("virtual data center up: 4 nodes on dc-internal "
              "(no published ports; reach via `docker compose exec` "
              "or attach a lab proxy)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
