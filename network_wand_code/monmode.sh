#!/usr/bin/env bash
# Put the Archer (wlan1) into monitor mode on a channel.  Usage: sudo ./monmode.sh [iface] [channel]
set -euo pipefail
IFACE="${1:-wlan1}"
CH="${2:-6}"
# Stop NetworkManager from grabbing the adapter (Raspberry Pi OS Bookworm uses NetworkManager)
nmcli device set "$IFACE" managed no 2>/dev/null || true
ip link set "$IFACE" down
iw dev "$IFACE" set type monitor
ip link set "$IFACE" up
iw dev "$IFACE" set channel "$CH"
iw dev "$IFACE" info | grep -E "type|channel"
