#!/usr/bin/env python3
"""
Sentinel Rover - Network Wand
Raspberry Pi Zero 2 W + TP-Link Archer T4U Plus (monitor mode on wlan1).

Threads:
  sniffer  - scapy AsyncSniffer on wlan1, updates RSSI / frames / deauths / APs
  roller   - once per second: frames/s, prunes old APs, channel hopping in Scan
  backend  - polls POST /api/wand for a target, sends telemetry and acks
  main     - draws the OLED, drives LEDs + buzzer, handles buttons

Run:  sudo .venv/bin/python wand.py            (real hardware)
      sudo .venv/bin/python wand.py --no-hw    (console output, no OLED/LEDs/buttons)
"""
import argparse
import collections
import logging
import os
import socket
import subprocess
import sys
import threading
import time

import requests
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = yaml.safe_load(open(os.path.join(HERE, "config.yaml")))
log = logging.getLogger("wand")

MODES = ["HUNT", "MONITOR", "SCAN", "STATUS"]


# --------------------------------------------------------------------------
# Shared state
# --------------------------------------------------------------------------
class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.mode = 0
        # target
        self.target_bssid = ""
        self.target_rack = ""
        self.target_channel = CFG["home_channel"]
        self.target_source = None          # "backend" | "local" | None
        # measurements
        self.rssi_ema = None
        self.rssi_seen = 0.0
        self.rssi_hist = collections.deque(maxlen=40)   # (t, ema)
        self.frames = 0
        self.fps = 0.0
        self.beacons = 0
        self.beacons_ps = 0.0
        self.deauth_times = collections.deque(maxlen=500)
        self.aps = {}                       # bssid -> dict(ssid, rssi, ch, seen)
        self.channel = CFG["home_channel"]
        # backend
        self.backend_ok = False
        self.backend_seen = 0.0
        self.pending_ack = False
        # ui
        self.scan_sel = 0
        self.toast = ""
        self.toast_until = 0.0
        self.running = True

    def say(self, text, secs=1.5):
        self.toast, self.toast_until = text, time.time() + secs

    def deauths_recent(self, window=3.0):
        cut = time.time() - window
        return sum(1 for t in self.deauth_times if t >= cut)

    def trend(self):
        if len(self.rssi_hist) < 4 or self.rssi_ema is None:
            return ""
        now = time.time()
        old = [v for t, v in self.rssi_hist if now - t >= 2.0]
        if not old:
            return ""
        d = self.rssi_ema - old[-1]
        return "closer" if d > 2 else ("further" if d < -2 else "steady")


S = State()


# --------------------------------------------------------------------------
# Radio helpers
# --------------------------------------------------------------------------
def set_channel(ch):
    iface = CFG["monitor_iface"]
    try:
        subprocess.run(["iw", "dev", iface, "set", "channel", str(ch)],
                       check=True, capture_output=True, timeout=2)
        with S.lock:
            S.channel = ch
    except Exception as e:  # noqa: BLE001
        log.warning("channel %s failed: %s", ch, e)


def wlan0_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "no link"


# --------------------------------------------------------------------------
# Sniffer
# --------------------------------------------------------------------------
def start_sniffer():
    from scapy.all import AsyncSniffer, Dot11, Dot11Beacon, Dot11Deauth, Dot11Disas, Dot11Elt, Dot11ProbeResp

    def ssid_of(pkt):
        elt = pkt.getlayer(Dot11Elt)
        while elt is not None:
            if elt.ID == 0:
                try:
                    return elt.info.decode(errors="ignore") or "<hidden>"
                except Exception:  # noqa: BLE001
                    return "?"
            elt = elt.payload.getlayer(Dot11Elt)
        return "?"

    def handle(pkt):
        if not pkt.haslayer(Dot11):
            return
        now = time.time()
        d = pkt[Dot11]
        rssi = getattr(pkt, "dBm_AntSignal", None)
        with S.lock:
            S.frames += 1
            if pkt.haslayer(Dot11Deauth) or pkt.haslayer(Dot11Disas):
                S.deauth_times.append(now)
            if pkt.haslayer(Dot11Beacon) or pkt.haslayer(Dot11ProbeResp):
                S.beacons += 1
                if d.addr3 and rssi is not None:
                    ap = S.aps.get(d.addr3, {"ssid": ssid_of(pkt)})
                    ap.update(rssi=rssi, ch=S.channel, seen=now)
                    S.aps[d.addr3] = ap
            # any frame transmitted by the target updates the hunt RSSI
            tgt = S.target_bssid
            if tgt and rssi is not None and d.addr2 and d.addr2.lower() == tgt:
                a = CFG["hunt"]["smoothing"]
                S.rssi_ema = rssi if S.rssi_ema is None else a * rssi + (1 - a) * S.rssi_ema
                S.rssi_seen = now
                S.rssi_hist.append((now, S.rssi_ema))

    sn = AsyncSniffer(iface=CFG["monitor_iface"], prn=handle, store=False)
    sn.start()
    log.info("sniffer running on %s", CFG["monitor_iface"])
    return sn


def roller():
    hop_i, last_hop, last_tick = 0, 0.0, time.time()
    while S.running:
        time.sleep(0.25)
        now = time.time()
        mode = MODES[S.mode]
        # channel: hop in Scan, otherwise sit on the target/home channel
        if mode == "SCAN" and now - last_hop > CFG["scan_dwell_s"]:
            chs = CFG["scan_channels"]
            hop_i = (hop_i + 1) % len(chs)
            set_channel(chs[hop_i])
            last_hop = now
        elif mode != "SCAN":
            want = S.target_channel if S.target_bssid else CFG["home_channel"]
            if S.channel != want:
                set_channel(want)
        # once per second: rates + pruning
        if now - last_tick >= 1.0:
            dt, last_tick = now - last_tick, now
            with S.lock:
                S.fps, S.frames = round(S.frames / dt, 1), 0
                S.beacons_ps, S.beacons = round(S.beacons / dt, 1), 0
                for b in [b for b, ap in S.aps.items() if now - ap["seen"] > CFG["ap_timeout_s"]]:
                    del S.aps[b]
                if now - S.rssi_seen > 5:
                    S.rssi_ema = None


# --------------------------------------------------------------------------
# Backend
# --------------------------------------------------------------------------
def backend_loop():
    url = CFG["backend_url"].rstrip("/") + "/api/wand"
    while S.running:
        with S.lock:
            body = {
                "wand_id": CFG["wand_id"],
                "rack_id": S.target_rack,
                "bssid": S.target_bssid,
                "rssi": None if S.rssi_ema is None else round(S.rssi_ema, 1),
                "mode": MODES[S.mode],
                "frames_per_s": S.fps,
                "deauths_3s": S.deauths_recent(),
                "ack": S.pending_ack,
            }
        try:
            r = requests.post(url, json=body, timeout=2)
            r.raise_for_status()
            data = r.json() if r.content else {}
            with S.lock:
                S.backend_ok, S.backend_seen = True, time.time()
                if body["ack"]:
                    S.pending_ack = False
                    S.say("Alert cleared")
                    if S.target_source == "backend":
                        S.target_bssid, S.target_rack = "", ""
                bssid = (data.get("bssid") or "").lower()
                if bssid and bssid != S.target_bssid:
                    S.target_bssid = bssid
                    S.target_rack = data.get("rack_id") or ""
                    S.target_channel = int(data.get("channel") or CFG["home_channel"])
                    S.target_source = "backend"
                    S.rssi_ema, S.rssi_hist = None, collections.deque(maxlen=40)
                    S.mode = 0
                    S.say("New target " + (S.target_rack or bssid[-8:]), 2.5)
        except Exception as e:  # noqa: BLE001
            with S.lock:
                S.backend_ok = time.time() - S.backend_seen < 10
            log.debug("backend: %s", e)
        time.sleep(CFG["poll_seconds"])


# --------------------------------------------------------------------------
# Hardware: OLED, LEDs, buzzer, buttons (each optional)
# --------------------------------------------------------------------------
class Hardware:
    def __init__(self, enabled):
        self.oled = self.pixels = self.buzzer = None
        self.font = None
        if not enabled:
            return
        try:
            from luma.core.interface.serial import i2c
            from luma.oled.device import ssd1306
            from PIL import ImageFont
            self.oled = ssd1306(i2c(port=CFG["oled"]["i2c_port"], address=CFG["oled"]["address"]))
            self.font = ImageFont.load_default()
        except Exception as e:  # noqa: BLE001
            log.warning("OLED off: %s", e)
        try:
            import board
            import neopixel_spi
            self.pixels = neopixel_spi.NeoPixel_SPI(board.SPI(), CFG["leds"]["count"],
                                                    brightness=CFG["leds"]["brightness"],
                                                    pixel_order=neopixel_spi.GRB, auto_write=False)
        except Exception as e:  # noqa: BLE001
            log.warning("LEDs off: %s", e)
        try:
            from gpiozero import Buzzer
            self.buzzer = Buzzer(CFG["pins"]["buzzer"])
        except Exception as e:  # noqa: BLE001
            log.warning("buzzer off: %s", e)

    def leds(self, rgb):
        if self.pixels:
            self.pixels.fill(rgb)
            self.pixels.show()

    def click(self, ms=8):
        if self.buzzer:
            self.buzzer.on()
            time.sleep(ms / 1000)
            self.buzzer.off()


def setup_buttons(hw_enabled):
    if not hw_enabled:
        return []
    from gpiozero import Button
    btns = []
    for name, pin in (("b1", CFG["pins"]["button1"]), ("b2", CFG["pins"]["button2"])):
        b = Button(pin, pull_up=True, bounce_time=0.03, hold_time=CFG["long_press_s"])
        b.was_held = False
        b.when_held = lambda b=b, n=name: (setattr(b, "was_held", True), on_button(n, True))
        b.when_released = lambda b=b, n=name: (on_button(n, False) if not b.was_held else None,
                                               setattr(b, "was_held", False))
        btns.append(b)
    return btns


def strongest_ap():
    if not S.aps:
        return None, None
    b, ap = max(S.aps.items(), key=lambda kv: kv[1]["rssi"])
    return b, ap


def lock_target(bssid, ap):
    S.target_bssid, S.target_rack = bssid, ""
    S.target_channel = ap.get("ch", S.channel)
    S.target_source = "local"
    S.rssi_ema, S.rssi_hist = None, collections.deque(maxlen=40)
    S.mode = 0
    S.say("Locked " + ap["ssid"][:12], 2)


def on_button(name, long_press):
    with S.lock:
        mode = MODES[S.mode]
        if name == "b1":
            S.mode = 0 if long_press else (S.mode + 1) % len(MODES)
            return
        # button 2
        if long_press and mode != "SCAN":
            S.pending_ack = True
            S.say("Clearing alert...")
        elif mode == "SCAN":
            ranked = sorted(S.aps.items(), key=lambda kv: kv[1]["rssi"], reverse=True)[:4]
            if not ranked:
                return
            if long_press:
                b, ap = ranked[min(S.scan_sel, len(ranked) - 1)]
                lock_target(b, ap)
            else:
                S.scan_sel = (S.scan_sel + 1) % len(ranked)
        elif mode == "HUNT" and not S.target_bssid:
            b, ap = strongest_ap()
            if b:
                lock_target(b, ap)
            else:
                S.say("No APs heard yet")


# --------------------------------------------------------------------------
# Screen content
# --------------------------------------------------------------------------
def screen_lines():
    with S.lock:
        mode = MODES[S.mode]
        head = f"{mode:<8}{'NET' if S.backend_ok else 'OFF':>4} ch{S.channel}"
        if time.time() < S.toast_until:
            return [head, "", S.toast], None
        if mode == "HUNT":
            if not S.target_bssid:
                return [head, "No target", "B2: lock strongest", "or wait for rover"], None
            r = S.rssi_ema
            rtxt = "--" if r is None else f"{r:.0f} dBm"
            return [head, (S.target_rack or "local target"), S.target_bssid,
                    f"RSSI {rtxt}  {S.trend()}"], r
        if mode == "MONITOR":
            return [head, f"frames/s {S.fps:.0f}", f"beacons/s {S.beacons_ps:.0f}",
                    f"deauth 3s {S.deauths_recent()}", f"APs heard {len(S.aps)}"], None
        if mode == "SCAN":
            ranked = sorted(S.aps.items(), key=lambda kv: kv[1]["rssi"], reverse=True)[:4]
            lines = [head]
            for i, (b, ap) in enumerate(ranked):
                mark = ">" if i == S.scan_sel else " "
                lines.append(f"{mark}{ap['ssid'][:9]:<9}{ap['rssi']:>4} {b[-5:]}")
            return lines or [head, "scanning..."], None
        return [head, f"IP {wlan0_ip()}", f"backend {'ok' if S.backend_ok else 'down'}",
                f"wand {CFG['wand_id']}", f"up {int(time.monotonic() // 60)} min"], None


def rssi_color(r):
    lo, hi = CFG["hunt"]["rssi_far"], CFG["hunt"]["rssi_near"]
    t = 0.0 if r is None else max(0.0, min(1.0, (r - lo) / (hi - lo)))
    if t < 0.5:                        # blue -> cyan
        return (0, int(510 * t), 255)
    return (0, 255, int(255 * (1 - (t - 0.5) * 2)))   # cyan -> green


def click_interval(r):
    lo, hi = CFG["hunt"]["rssi_far"], CFG["hunt"]["rssi_near"]
    t = max(0.0, min(1.0, (r - lo) / (hi - lo)))
    return 1.0 - t * 0.94             # 1.0 s far ... 0.06 s near


# --------------------------------------------------------------------------
# Main loop
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-hw", action="store_true", help="console output, no OLED/LEDs/buttons")
    ap.add_argument("--no-sniff", action="store_true", help="skip the sniffer (UI/backend test)")
    ap.add_argument("-v", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.v else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    if os.geteuid() != 0 and not args.no_sniff:
        sys.exit("Run with sudo: the sniffer needs raw sockets.")

    hw = Hardware(not args.no_hw)
    buttons = setup_buttons(not args.no_hw)  # noqa: F841  (keep references alive)
    sniffer = None if args.no_sniff else start_sniffer()
    set_channel(CFG["home_channel"])
    for fn in (roller, backend_loop):
        threading.Thread(target=fn, daemon=True).start()

    last_click, last_print = 0.0, 0.0
    try:
        while True:
            lines, rssi = screen_lines()
            mode = MODES[S.mode]
            now = time.time()
            # LEDs + buzzer
            if S.deauths_recent() >= CFG["deauth_alert"] and int(now * 4) % 2:
                hw.leds((255, 0, 0))
            elif mode == "HUNT" and S.target_bssid:
                hw.leds(rssi_color(rssi))
                if rssi is not None and now - last_click > click_interval(rssi):
                    hw.click()
                    last_click = now
            elif mode == "STATUS":
                lvl = int(60 + 60 * abs((now % 2) - 1))
                hw.leds((0, lvl, lvl))
            else:
                hw.leds((0, 0, 0))
            # screen
            if hw.oled:
                from luma.core.render import canvas
                with canvas(hw.oled) as draw:
                    for i, line in enumerate(lines[:6]):
                        draw.text((0, i * 10), line, fill="white", font=hw.font)
                    if rssi is not None:                       # signal bar on the bottom row
                        lo, hi = CFG["hunt"]["rssi_far"], CFG["hunt"]["rssi_near"]
                        w = int(127 * max(0, min(1, (rssi - lo) / (hi - lo))))
                        draw.rectangle((0, 58, w, 63), fill="white")
            elif now - last_print > 1:
                print(" | ".join(lines))
                last_print = now
            time.sleep(0.12)
    except KeyboardInterrupt:
        pass
    finally:
        S.running = False
        hw.leds((0, 0, 0))
        if sniffer:
            sniffer.stop()


if __name__ == "__main__":
    main()
