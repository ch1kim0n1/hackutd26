#!/usr/bin/env python3
"""Run the local dashboard using the existing physical-demo identity."""
import json
import os
from pathlib import Path

root = Path(__file__).resolve().parents[2]
physical = dict(line.split('=', 1) for line in (root / 'deploy/env/physical.env').read_text().splitlines() if '=' in line)
tokens = json.loads((root / 'deploy/secrets/identities.json').read_text())[physical['SPACETIMEDB_URI']]
env = os.environ.copy()
env.update({
    'VITE_ROVER_CAMERA_URL': 'http://127.0.0.1:18080',
    'VITE_SPACETIMEDB_URI': 'http://127.0.0.1:3000',
    'VITE_SPACETIMEDB_DATABASE': physical['SPACETIMEDB_DATABASE'],
    'VITE_SPACETIMEDB_TOKEN': tokens['commander'],
})
os.chdir(root / 'apps/dashboard/twin')
os.execvpe('npm', ['npm', 'run', 'dev', '--', '--port', '5188', '--strictPort'], env)
