"""Loopback-only parked gimbal controller. Run alongside the existing snapshot service."""
import argparse
import base64
import hashlib
import io
import json
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import urlopen

from PIL import Image, ImageDraw

def grid_jpeg(jpg):
    im = Image.open(io.BytesIO(jpg)).convert("RGB")
    w, h = im.size
    draw = ImageDraw.Draw(im)
    for i in (1, 2):
        draw.line((i*w//3, 0, i*w//3, h), fill="white")
        draw.line((0, i*h//3, w, i*h//3), fill="white")
    for i in range(9):
        x, y = i%3*w//3+3, i//3*h//3+3
        draw.rectangle((x,y,x+14,y+15), fill="black")
        draw.text((x+2,y+1), str(i+1), fill="white")
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85)
    return base64.b64encode(out.getvalue()).decode("ascii")

def step(cell, pan, tilt, right_sign, down_sign):
    if cell in ("none", "ambiguous"):
        return pan, tilt
    if cell not in tuple(str(i) for i in range(1,10)):
        raise ValueError("invalid cell")
    row, col = divmod(int(cell)-1, 3)
    return (max(-15,min(15,pan + (col-1)*right_sign*4)),
            max(-8,min(8,tilt + (row-1)*down_sign*3)))

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--move", action="store_true")
    p.add_argument("--right-sign", type=int, choices=(-1,1))
    p.add_argument("--down-sign", type=int, choices=(-1,1))
    args = p.parse_args()
    if args.move and None in (args.right_sign,args.down_sign):
        p.error("set both signs from the physical mount")
    car = None
    if args.move:
        from picarx import Picarx
        car = Picarx()
    pan = tilt = 0
    pending = None
    last_hash = None
    ready = 0
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, data):
            raw = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def do_GET(self):
            nonlocal pending,last_hash
            if self.path != "/frame":
                return self.reply(404,{})
            pending = None
            if time.monotonic()<ready:
                return self.reply(409,{"error":"settling"})
            try:
                with urlopen("http://127.0.0.1:18080/snapshot.jpg",timeout=3) as r:
                    jpg=r.read(4_000_001)
                if len(jpg)>4_000_000:
                    raise ValueError("oversize")
                digest=hashlib.sha256(jpg).digest()
                if digest==last_hash:
                    return self.reply(409,{"error":"identical snapshot; check feed"})
                img=grid_jpeg(jpg)
                last_hash=digest
                pending=(uuid.uuid4().hex,time.monotonic())
                self.reply(200,{"id":pending[0],"jpeg":img,"pan":pan,"tilt":tilt})
            except (ValueError,OSError) as e:
                self.reply(503,{"error":str(e)})
        def do_POST(self):
            nonlocal pan,tilt,pending,ready
            if self.path!="/observation":
                return self.reply(404,{})
            try:
                size=int(self.headers.get("Content-Length",0))
                if not 0<size<=1024:
                    raise ValueError("invalid size")
                msg=json.loads(self.rfile.read(size))
                if not pending or msg["id"]!=pending[0] or time.monotonic()-pending[1]>20:
                    return self.reply(409,{"error":"expired or superseded frame"})
                pending=None
                new=step(msg["cell"],pan,tilt,args.right_sign or 1,args.down_sign or 1)
            except (ValueError,TypeError,KeyError) as e:
                return self.reply(400,{"error":str(e)})
            if car and new!=(pan,tilt):
                car.set_cam_pan_angle(new[0])
                car.set_cam_tilt_angle(new[1])
                pan,tilt=new
                ready=time.monotonic()+0.6
            self.reply(200,{"cell":msg["cell"],"move_enabled":bool(car),
                            "requested_deg":new,"pan_deg":pan,"tilt_deg":tilt})
    try:
        if car:
            car.stop()
            car.set_cam_pan_angle(0)
            car.set_cam_tilt_angle(0)
            ready=time.monotonic()+0.6
        with HTTPServer(("127.0.0.1",18110),Handler) as srv:
            print("Tracker ready on 18110. Ctrl+C to quit.",flush=True)
            srv.serve_forever()
    finally:
        if car:
            car.stop()
            car.set_cam_pan_angle(0)
            car.set_cam_tilt_angle(0)

if __name__=="__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
