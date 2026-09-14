#!/usr/bin/env bash
# Launch PX4 SITL instances: one multirotor (x500) and one rover (ackermann).
#
# Each instance gets a distinct MAVLink UDP port, uXRCE-DDS client port, and
# ROS 2 namespace so both appear as separate vehicles on the same DDS domain.
#
# Requirements:
#   - PX4-Autopilot cloned at $PX4_DIR (default: ~/PX4-Autopilot)
#   - Gazebo Garden installed and sourced
#   - PX4 built: cd $PX4_DIR && make px4_sitl_default
#   - micro-xrce-dds-agent running (or start with: MicroXRCEAgent udp4 -p 8888)
#
# Usage:
#   PX4_DIR=/opt/PX4-Autopilot ./scripts/launch_sitl.sh
#   HEADLESS=1 ./scripts/launch_sitl.sh   # suppress Gazebo GUI

set -euo pipefail

PX4_DIR="${PX4_DIR:-$HOME/PX4-Autopilot}"
PX4_BIN="${PX4_DIR}/build/px4_sitl_default/bin/px4"
HEADLESS="${HEADLESS:-0}"
READY_TIMEOUT="${READY_TIMEOUT:-60}"

if [ ! -x "$PX4_BIN" ]; then
  echo "[launch_sitl] ERROR: PX4 binary not found at $PX4_BIN" >&2
  echo "[launch_sitl]        Run: cd $PX4_DIR && make px4_sitl_default" >&2
  exit 1
fi

LOG_DIR="${TMPDIR:-/tmp}/px4_sitl_logs"
mkdir -p "$LOG_DIR"
UAV_LOG="$LOG_DIR/uav1.log"
GND_LOG="$LOG_DIR/gnd1.log"

# Export Gazebo headless flag
if [ "$HEADLESS" = "1" ]; then
  export LIBGL_ALWAYS_SOFTWARE=1
  export DISPLAY="${DISPLAY:-:99}"
fi

echo "[launch_sitl] Starting multirotor SITL (gz_x500) ..."
echo "[launch_sitl]   MAVLink UDP: 14540 | uXRCE port: 8888 | ROS 2 ns: /px4_1"
(
  cd "$PX4_DIR"
  PX4_SYS_AUTOSTART=4001 \
  PX4_GZ_MODEL=x500 \
  PX4_MICRODDS_NS=/px4_1 \
  "$PX4_BIN" -i 1 -d
) > "$UAV_LOG" 2>&1 &
UAV_PID=$!

echo "[launch_sitl] Starting rover SITL (gz_rover_ackermann) ..."
echo "[launch_sitl]   MAVLink UDP: 14541 | uXRCE port: 8888 | ROS 2 ns: /px4_2"
(
  cd "$PX4_DIR"
  PX4_SYS_AUTOSTART=4009 \
  PX4_GZ_MODEL=rover_ackermann \
  PX4_MICRODDS_NS=/px4_2 \
  "$PX4_BIN" -i 2 -d
) > "$GND_LOG" 2>&1 &
GND_PID=$!

echo "[launch_sitl] PIDs — UAV: $UAV_PID  Rover: $GND_PID"
echo "[launch_sitl] Logs — UAV: $UAV_LOG  Rover: $GND_LOG"

# Wait for both instances to report startup success
echo "[launch_sitl] Waiting for SITL instances to become ready (timeout: ${READY_TIMEOUT}s) ..."

_wait_ready() {
  local log="$1"
  local label="$2"
  local deadline=$(( $(date +%s) + READY_TIMEOUT ))
  until grep -q "Startup script returned successfully\|Ready for takeoff\|INFO  [Simulator] Simulator connected" "$log" 2>/dev/null; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
      echo "[launch_sitl] WARNING: $label did not report ready within ${READY_TIMEOUT}s" >&2
      return 1
    fi
    sleep 1
  done
  echo "[launch_sitl] $label is ready."
}

_wait_ready "$UAV_LOG" "Multirotor (UAV-1)" || true
_wait_ready "$GND_LOG" "Rover (GND-1)"      || true

echo "[launch_sitl] Both SITL instances started."
echo "[launch_sitl] Press Ctrl+C to stop."

cleanup() {
  echo ""
  echo "[launch_sitl] Stopping SITL instances (PIDs: $UAV_PID $GND_PID) ..."
  kill "$UAV_PID" "$GND_PID" 2>/dev/null || true
  wait "$UAV_PID" "$GND_PID" 2>/dev/null || true
  echo "[launch_sitl] Stopped."
}
trap cleanup INT TERM EXIT

wait
