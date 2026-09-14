#!/usr/bin/env bash
# Launch PX4 SITL instances for multirotor (x500) and rover (ackermann).
#
# Requirements:
#   - PX4-Autopilot cloned at $PX4_DIR (default: ~/PX4-Autopilot)
#   - Gazebo Garden installed and sourced
#   - PX4 built: cd $PX4_DIR && make px4_sitl_default
#
# Usage:
#   PX4_DIR=/opt/PX4-Autopilot ./scripts/launch_sitl.sh

set -euo pipefail

PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"
PX4_BIN="${PX4_DIR}/build/px4_sitl_default/bin/px4"

if [ ! -x "$PX4_BIN" ]; then
  echo "[launch_sitl] ERROR: PX4 binary not found at $PX4_BIN" >&2
  echo "[launch_sitl]        Run: cd $PX4_DIR && make px4_sitl_default" >&2
  exit 1
fi

echo "[launch_sitl] Starting multirotor SITL (gz_x500) — MAVLink UDP 14540, 14580..."
cd "$PX4_DIR"
PX4_SYS_AUTOSTART=4001 PX4_GZ_MODEL=x500 \
    "$PX4_BIN" -i 1 -d &
UAV_PID=$!

echo "[launch_sitl] Starting rover SITL (gz_rover_ackermann) — MAVLink UDP 14541, 14581..."
PX4_SYS_AUTOSTART=4009 PX4_GZ_MODEL=rover_ackermann \
    "$PX4_BIN" -i 2 -d &
GND_PID=$!

echo "[launch_sitl] Both SITL instances started."
echo "[launch_sitl]   Multirotor PID: $UAV_PID  (UDP 14540)"
echo "[launch_sitl]   Rover      PID: $GND_PID  (UDP 14541)"
echo "[launch_sitl] Press Ctrl+C to stop both instances."

cleanup() {
  echo ""
  echo "[launch_sitl] Stopping SITL instances..."
  kill "$UAV_PID" "$GND_PID" 2>/dev/null || true
  echo "[launch_sitl] Stopped."
}
trap cleanup INT TERM

wait
