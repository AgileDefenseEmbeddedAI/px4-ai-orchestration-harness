#!/usr/bin/env bash
# inject_link_loss.sh — Simulate GCS link loss for SITL contingency testing.
#
# Blocks the GCS-side UDP port(s) used by the SITL MAVLink bridge by adding
# iptables DROP rules for outbound traffic to the vehicle SITL ports.
# Restores the rules (or uses a timed restore) after DURATION_S seconds.
#
# Usage:
#   ./scripts/inject_link_loss.sh [DURATION_S] [UAV_PORT] [ROVER_PORT]
#
#   DURATION_S  — seconds to hold the link down (default 60)
#   UAV_PORT    — SITL UDP port for multirotor (default 14540)
#   ROVER_PORT  — SITL UDP port for rover      (default 14541)
#
# Requirements: iptables (Linux); must run as root or with CAP_NET_ADMIN.
# In CI / unit-test mode the script is not invoked — the executor is tested
# via Python's time-manipulation mocks instead.

set -euo pipefail

DURATION_S="${1:-60}"
UAV_PORT="${2:-14540}"
ROVER_PORT="${3:-14541}"

echo "[inject_link_loss] Injecting link loss for ${DURATION_S}s (ports ${UAV_PORT}, ${ROVER_PORT})"

# Drop outbound UDP to SITL vehicle ports (GCS → vehicle direction)
iptables -I OUTPUT -p udp --dport "${UAV_PORT}"   -j DROP
iptables -I OUTPUT -p udp --dport "${ROVER_PORT}" -j DROP

cleanup() {
    echo "[inject_link_loss] Restoring link (removing DROP rules)"
    iptables -D OUTPUT -p udp --dport "${UAV_PORT}"   -j DROP 2>/dev/null || true
    iptables -D OUTPUT -p udp --dport "${ROVER_PORT}" -j DROP 2>/dev/null || true
    echo "[inject_link_loss] Link restored"
}

# Always restore on exit (normal, error, or Ctrl-C)
trap cleanup EXIT

echo "[inject_link_loss] Link down — waiting ${DURATION_S}s"
sleep "${DURATION_S}"
# cleanup runs via trap
