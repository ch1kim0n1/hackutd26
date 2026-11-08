#!/usr/bin/env python3
from pathlib import Path
from html import escape
import cairosvg

OUT = Path(__file__).resolve().parent
W, H = 1920, 900
BG = "#111210"
PANEL = "#191a17"
CARD = "#23241f"
BORDER = "#4b4c44"
WHITE = "#f4f2e9"
MUTED = "#b0b1a8"
GRAY = "#c5c6bd"
YELLOW = "#f2c94c"


def text(x, y, value, size=22, color=MUTED, weight=400, anchor="start"):
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{escape(value)}</text>'


def icon(kind, x, y, color):
    common = f'fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"'
    if kind == "server":
        return f'<g {common}><rect x="{x}" y="{y}" width="48" height="54" rx="6"/><path d="M{x+8} {y+17}H{x+40}M{x+8} {y+35}H{x+40}"/><circle cx="{x+13}" cy="{y+9}" r="2" fill="{color}"/><circle cx="{x+13}" cy="{y+27}" r="2" fill="{color}"/><circle cx="{x+13}" cy="{y+45}" r="2" fill="{color}"/></g>'
    if kind == "sensor":
        return f'<g {common}><circle cx="{x+24}" cy="{y+28}" r="6"/><path d="M{x+13} {y+17}A16 16 0 0 0 {x+13} {y+39}M{x+35} {y+17}A16 16 0 0 1 {x+35} {y+39}M{x+5} {y+9}A27 27 0 0 0 {x+5} {y+47}M{x+43} {y+9}A27 27 0 0 1 {x+43} {y+47}"/></g>'
    if kind == "rover":
        return f'<g {common}><rect x="{x+5}" y="{y+18}" width="42" height="25" rx="6"/><path d="M{x+15} {y+18}V{y+8}H{x+37}V{y+18}M{x+26} {y+8}V{y+2}"/><circle cx="{x+13}" cy="{y+48}" r="7"/><circle cx="{x+39}" cy="{y+48}" r="7"/><circle cx="{x+17}" cy="{y+29}" r="3"/><path d="M{x+31} {y+29}H{x+40}"/></g>'
    if kind == "gateway":
        return f'<g {common}><path d="M{x+26} {y+2}L{x+46} {y+10}V{y+25}C{x+46} {y+40} {x+37} {y+49} {x+26} {y+54}C{x+15} {y+49} {x+6} {y+40} {x+6} {y+25}V{y+10}Z"/><path d="M{x+16} {y+28}L{x+23} {y+35}L{x+37} {y+19}"/></g>'
    if kind == "database":
        return f'<g {common}><ellipse cx="{x+26}" cy="{y+10}" rx="20" ry="8"/><path d="M{x+6} {y+10}V{y+43}C{x+6} {y+48} {x+15} {y+52} {x+26} {y+52}C{x+37} {y+52} {x+46} {y+48} {x+46} {y+43}V{y+10}M{x+6} {y+27}C{x+6} {y+32} {x+15} {y+36} {x+26} {y+36}C{x+37} {y+36} {x+46} {y+32} {x+46} {y+27}"/></g>'
    if kind == "ai":
        return f'<g {common}><rect x="{x+8}" y="{y+8}" width="36" height="36" rx="8"/><path d="M{x+17} {y+2}V{y+8}M{x+35} {y+2}V{y+8}M{x+17} {y+44}V{y+50}M{x+35} {y+44}V{y+50}M{x+2} {y+17}H{x+8}M{x+2} {y+35}H{x+8}M{x+44} {y+17}H{x+50}M{x+44} {y+35}H{x+50}"/><circle cx="{x+20}" cy="{y+24}" r="2.5" fill="{color}"/><circle cx="{x+33}" cy="{y+24}" r="2.5" fill="{color}"/><path d="M{x+20} {y+34}H{x+33}"/></g>'
    if kind == "mission":
        return f'<g {common}><path d="M{x+4} {y+43}H{x+48}M{x+10} {y+43}V{y+24}M{x+42} {y+43}V{y+24}M{x+10} {y+25}C{x+17} {y+7} {x+35} {y+7} {x+42} {y+25}M{x+19} {y+43}V{y+30}M{x+33} {y+43}V{y+30}"/></g>'
    if kind == "human":
        return f'<g {common}><circle cx="{x+26}" cy="{y+13}" r="9"/><path d="M{x+8} {y+49}C{x+10} {y+34} {x+17} {y+28} {x+26} {y+28}C{x+35} {y+28} {x+42} {y+34} {x+44} {y+49}M{x+17} {y+38}L{x+24} {y+44}L{x+37} {y+31}"/></g>'
    return ""


def card(x, y, w, h, title, subtitle, glyph, accent=GRAY, title_size=30):
    out = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="{CARD}" stroke="{BORDER}" stroke-width="2"/>'
    out += f'<rect x="{x}" y="{y}" width="7" height="{h}" rx="3.5" fill="{accent}"/>'
    out += f'<rect x="{x+22}" y="{y+25}" width="70" height="70" rx="16" fill="{accent}" opacity=".1"/>'
    out += icon(glyph, x+31, y+33, accent)
    out += text(x+112, y+57, title, title_size, WHITE, 700)
    out += text(x+112, y+94, subtitle, 20, MUTED, 500)
    return out


def arrow(path, color=GRAY, dashed=False):
    marker = "arrowYellow" if color == YELLOW else "arrowGray"
    dash = 'stroke-dasharray="12 10"' if dashed else ""
    return f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" {dash} marker-end="url(#{marker})"/>'


def label(x, y, value, color=MUTED):
    width = len(value) * 10 + 24
    return f'<rect x="{x-width/2}" y="{y-27}" width="{width}" height="38" rx="9" fill="{BG}"/>' + text(x, y, value, 18, color, 600, "middle")


svg = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="BlindSpot high level software and hardware architecture">
<defs>
<linearGradient id="bg" x2="1" y2="1"><stop stop-color="{BG}"/><stop offset="1" stop-color="#1b1c18"/></linearGradient>
<marker id="arrowGray" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0 0L8 3L0 6Z" fill="{GRAY}"/></marker>
<marker id="arrowYellow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0 0L8 3L0 6Z" fill="{YELLOW}"/></marker>
</defs>
<rect width="{W}" height="{H}" fill="url(#bg)"/>
<g font-family="Inter, Segoe UI, Arial, sans-serif"><g transform="translate(0 -175)">''']

for x, w, number, title_value, accent in [(60, 370, "01", "PHYSICAL WORLD", GRAY), (460, 930, "02", "SOFTWARE + DECISION", GRAY), (1420, 440, "03", "COMMAND CENTER", YELLOW)]:
    svg += [f'<rect x="{x}" y="215" width="{w}" height="650" rx="22" fill="{PANEL}" stroke="{BORDER}" stroke-width="1.5"/>',
            f'<circle cx="{x+30}" cy="250" r="17" fill="{accent}" opacity=".15"/>' + text(x+30, 256, number, 15, accent, 700, "middle"),
            text(x+60, 257, title_value, 18, accent, 700)]

svg += [card(90, 295, 310, 145, "Server Stations", "2 Raspberry Pis", "server", GRAY, 27),
        card(90, 480, 310, 130, "Sensor Inputs", "WiFi · BLE · Cabinet", "sensor", GRAY, 27),
        card(90, 670, 310, 150, "PiCar X Rover", "Camera · LiDAR · Tags", "rover", YELLOW, 27),
        card(500, 295, 360, 150, "MQTT Gateway", "Mosquitto + TypeScript", "gateway", GRAY, 30),
        card(940, 295, 400, 150, "SpacetimeDB", "State + correlation", "database", GRAY, 32),
        card(650, 510, 500, 155, "AI Investigation", "Nemotron + FastAPI", "ai", YELLOW, 34),
        card(680, 710, 420, 125, "Mission Bridge", "Dispatch + evidence", "mission", YELLOW, 31),
        card(1460, 625, 360, 185, "Human Approval", "Commander decision", "human", YELLOW, 29)]

svg += [f'<rect x="1460" y="295" width="360" height="245" rx="18" fill="{CARD}" stroke="{BORDER}" stroke-width="2"/>',
        f'<rect x="1460" y="295" width="7" height="245" rx="3.5" fill="{YELLOW}"/>',
        text(1490, 348, "Phantom Command", 32, WHITE, 700),
        text(1490, 385, "Incidents · Twin · Rover", 20, MUTED, 500),
        f'<rect x="1490" y="414" width="300" height="94" rx="12" fill="{BG}" stroke="{BORDER}"/>',
        f'<rect x="1503" y="427" width="48" height="68" rx="6" fill="{PANEL}"/>',
        f'<rect x="1563" y="427" width="100" height="30" rx="6" fill="{PANEL}"/><rect x="1675" y="427" width="100" height="30" rx="6" fill="{PANEL}"/>',
        f'<rect x="1563" y="468" width="212" height="27" rx="6" fill="{PANEL}"/>',
        f'<path d="M1575 486L1605 477L1635 483L1665 474L1695 481L1730 473L1760 477" fill="none" stroke="{YELLOW}" stroke-width="2.5"/>',
        f'<circle cx="1518" cy="441" r="4" fill="{YELLOW}"/><circle cx="1518" cy="458" r="4" fill="{GRAY}"/><circle cx="1518" cy="475" r="4" fill="{GRAY}"/>']

svg += [arrow("M400 367H445V370H500"), label(447, 337, "Telemetry"),
        arrow("M400 545H445V405H500"),
        arrow("M860 370H940"),
        arrow("M1340 370H1460"), label(1400, 340, "Live state"),
        arrow("M1140 445V475H900V510"), label(1040, 470, "Incident"),
        arrow("M1150 585H1360V685H1460", YELLOW), label(1290, 560, "Proposal", YELLOW),
        arrow("M1460 755H1100", YELLOW), label(1280, 730, "Approved", YELLOW),
        arrow("M680 750H435V730H400", YELLOW, True), label(540, 718, "Mission", YELLOW),
        arrow("M400 790H435V800H680", GRAY, True), label(540, 828, "Evidence"),
        arrow("M1100 800H1350V420H1340"), label(1260, 490, "Reassess")]

svg += [f'<rect x="60" y="905" width="1800" height="92" rx="18" fill="{PANEL}" stroke="{BORDER}"/>',
        arrow("M250 945H305", GRAY), text(327, 953, "Telemetry + evidence", 20, WHITE, 600),
        arrow("M730 945H785", YELLOW), text(807, 953, "Proposal + mission", 20, WHITE, 600),
        arrow("M1210 945H1265", YELLOW, True), text(1287, 953, "Physical validation", 20, WHITE, 600),
        '</g></g></svg>']

data = "".join(svg)
(OUT / "06_blindspot_architecture.svg").write_text(data)
cairosvg.svg2png(bytestring=data.encode(), write_to=str(OUT / "06_blindspot_architecture.png"), output_width=W, output_height=H)
print(OUT / "06_blindspot_architecture.png")
