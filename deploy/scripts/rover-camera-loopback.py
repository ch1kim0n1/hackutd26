"""Run the rover's existing camera service privately through an SSH tunnel.

This wrapper runs on the rover via `python3 -u -`, reading its source from
standard input. It changes no rover files and never sends motion commands.
"""
import http.server
import os
import runpy
import sys
import threading
import time
from urllib.parse import urlsplit

if len(sys.argv) != 4:
    raise SystemExit('usage: python3 -u - PORT DASHBOARD_ORIGIN CAMERA_SERVICE_PATH')
port = int(sys.argv[1])
origin = sys.argv[2]
service_path = sys.argv[3]
parsed = urlsplit(origin)
if not 1 <= port <= 65535 or parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
    raise SystemExit('camera port or loopback dashboard origin invalid')

original_server = http.server.ThreadingHTTPServer
original_header = http.server.BaseHTTPRequestHandler.send_header

class LoopbackServer(original_server):
    def __init__(self, address, handler):
        super().__init__(('127.0.0.1', address[1]), handler)

def restricted_header(self, name, value):
    if name.lower() == 'access-control-allow-origin':
        value = origin
    return original_header(self, name, value)

http.server.ThreadingHTTPServer = LoopbackServer
http.server.BaseHTTPRequestHandler.send_header = restricted_header

# An SSH multiplexed client may exit without signalling its remote child.
# A small heartbeat detects the closed channel and stops the camera process.
def watch_channel():
    while True:
        time.sleep(10)
        try:
            print('camera tunnel active', flush=True)
        except (BrokenPipeError, OSError):
            os._exit(0)

threading.Thread(target=watch_channel, daemon=True).start()
sys.argv = [service_path, '--port', str(port)]
runpy.run_path(service_path, run_name='__main__')
