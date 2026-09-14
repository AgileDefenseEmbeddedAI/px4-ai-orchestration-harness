"""
Contingency ladder executor — REQ-LNK-01/02.

Runs on each vehicle's companion channel. Monitors the GCS heartbeat; when
the heartbeat goes silent beyond the timeout, reads the pre-embedded ladder
file and issues PX4 commands via local MAVLink loopback for each rung in
sequence.  Emits a local audit event for each rung executed.

This module MUST NOT import openai, requests, httpx, or any other network
client. It MUST NOT contact the harness API. All logic is local and
deterministic — no model inference, ever.

Ladder file format (YAML or JSON):
  rungs:
    - trigger: "link_loss_T+0"
      actions:
        - cmd: "loiter"
          params: {duration_s: 30}
    - trigger: "link_loss_T+30"
      actions:
        - cmd: "rtl"
          params: {}
    - trigger: "link_loss_T+60"
      actions:
        - cmd: "land"
          params: {}

Triggers are evaluated in rung order; the first rung whose elapsed-since-
link-loss time satisfies its threshold fires, remaining rungs are queued for
later evaluation.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import yaml

from harness.audit.logger import log_event

logger = logging.getLogger(__name__)

_TRIGGER_RE = re.compile(r"link_loss_T\+(\d+)")

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------


def load_ladder(path: str | Path) -> list[dict]:
    """Parse a YAML or JSON ladder file and return its rung list."""
    p = Path(path)
    text = p.read_text()
    if p.suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    rungs = data.get("rungs", [])
    if not isinstance(rungs, list):
        raise ValueError(f"Ladder file {path!r} must have a top-level 'rungs' list")
    return rungs


def _trigger_threshold(trigger: str) -> int:
    """Return seconds-after-link-loss for a 'link_loss_T+N' trigger string."""
    m = _TRIGGER_RE.fullmatch(trigger.strip())
    if not m:
        raise ValueError(f"Unrecognized trigger format: {trigger!r}")
    return int(m.group(1))


# ---------------------------------------------------------------------------
# Command dispatcher (stub — real impl sends MAVLink loopback)
# ---------------------------------------------------------------------------


def _execute_action(vehicle_id: str, action: dict[str, Any]) -> None:
    """
    Issue one ladder action to the vehicle.

    Real implementation would open a pymavlink loopback connection and send
    the appropriate MAV_CMD.  This stub logs the intent so the executor can
    run in CI without live SITL.
    """
    cmd = action.get("cmd", "unknown")
    params = action.get("params", {})
    logger.info(
        f"[contingency][{vehicle_id}] executing cmd={cmd!r} params={params}"
    )
    # Real MAVLink loopback (pymavlink) would go here:
    #   from pymavlink import mavutil
    #   mav = mavutil.mavlink_connection("udp:127.0.0.1:14540", source_system=255)
    #   mav.wait_heartbeat(timeout=5)
    #   if cmd == "loiter":
    #       mav.mav.command_long_send(target_system, target_component,
    #           mavutil.mavlink.MAV_CMD_NAV_LOITER_TIME, 0,
    #           params.get("duration_s", 30), 0, 0, 0, 0, 0, 0)
    #   elif cmd == "rtl":
    #       mav.mav.command_long_send(..., MAV_CMD_NAV_RETURN_TO_LAUNCH, ...)
    #   elif cmd == "land":
    #       mav.mav.command_long_send(..., MAV_CMD_NAV_LAND, ...)


# ---------------------------------------------------------------------------
# Core executor
# ---------------------------------------------------------------------------


class ContingencyExecutor:
    """
    Monitors heartbeat and autonomously executes a contingency ladder on
    link loss without any external network calls or LLM inference.

    Parameters
    ----------
    vehicle_id:
        Identifier for the vehicle this executor guards (used in audit records).
    mission_id:
        Mission identifier; audit events are written under this mission log.
    ladder:
        Parsed rung list (from load_ladder or constructed directly in tests).
    heartbeat_timeout_s:
        Seconds of silence before link loss is declared (default 5).
    """

    def __init__(
        self,
        vehicle_id: str,
        mission_id: str,
        ladder: list[dict],
        heartbeat_timeout_s: float = 5.0,
    ) -> None:
        self.vehicle_id = vehicle_id
        self.mission_id = mission_id
        self.ladder = ladder
        self.heartbeat_timeout_s = heartbeat_timeout_s

        self._last_heartbeat: float = time.monotonic()
        self._link_lost_at: float | None = None
        self._next_rung_index: int = 0
        self._link_healthy: bool = True

    # ------------------------------------------------------------------
    # Heartbeat interface — call this each time a heartbeat arrives
    # ------------------------------------------------------------------

    def record_heartbeat(self, now: float | None = None) -> None:
        """Update the last-seen heartbeat timestamp."""
        self._last_heartbeat = now if now is not None else time.monotonic()
        if not self._link_healthy:
            logger.info(
                f"[contingency][{self.vehicle_id}] link restored — "
                "executor stays in ladder-in-progress state"
            )
        self._link_healthy = True

    # ------------------------------------------------------------------
    # Tick — call this on a regular interval (e.g. 1 Hz) from your loop
    # ------------------------------------------------------------------

    def tick(self, now: float | None = None) -> list[dict]:
        """
        Evaluate heartbeat timeout and execute any due ladder rungs.

        Returns a list of audit event dicts for rungs executed this tick
        (empty if nothing fired).  The caller is responsible for calling
        this regularly; the executor itself does not spin a thread.
        """
        if now is None:
            now = time.monotonic()

        elapsed_since_hb = now - self._last_heartbeat

        if elapsed_since_hb < self.heartbeat_timeout_s:
            return []

        # Link loss detected on this tick (or previously)
        if self._link_lost_at is None:
            self._link_lost_at = self._last_heartbeat + self.heartbeat_timeout_s
            self._link_healthy = False
            logger.warning(
                f"[contingency][{self.vehicle_id}] link loss declared "
                f"(heartbeat silent {elapsed_since_hb:.1f}s)"
            )
            log_event(
                self.mission_id,
                "contingency_link_loss",
                {
                    "vehicle_id": self.vehicle_id,
                    "heartbeat_silent_s": elapsed_since_hb,
                },
            )

        elapsed_since_loss = now - self._link_lost_at
        fired: list[dict] = []

        while self._next_rung_index < len(self.ladder):
            rung = self.ladder[self._next_rung_index]
            threshold = _trigger_threshold(rung["trigger"])
            if elapsed_since_loss < threshold:
                break
            # Fire this rung
            self._next_rung_index += 1
            rung_event = self._fire_rung(rung, elapsed_since_loss)
            fired.append(rung_event)

        return fired

    def _fire_rung(self, rung: dict, elapsed_s: float) -> dict:
        trigger = rung["trigger"]
        actions = rung.get("actions", [])
        logger.info(
            f"[contingency][{self.vehicle_id}] firing rung trigger={trigger!r} "
            f"({len(actions)} action(s), elapsed={elapsed_s:.1f}s)"
        )
        for action in actions:
            _execute_action(self.vehicle_id, action)

        event_payload = {
            "vehicle_id": self.vehicle_id,
            "trigger": trigger,
            "elapsed_since_loss_s": elapsed_s,
            "actions": actions,
        }
        log_event(self.mission_id, "contingency_rung_executed", event_payload)
        return {"event": "contingency_rung_executed", "payload": event_payload}

    # ------------------------------------------------------------------
    # Convenience: run a blocking loop (for companion-channel deployment)
    # ------------------------------------------------------------------

    def run(self, tick_interval_s: float = 1.0) -> None:
        """
        Blocking loop — intended for deployment on a vehicle companion channel.

        The loop polls heartbeat and calls tick() at tick_interval_s cadence.
        Interrupt with Ctrl-C or SIGTERM.
        """
        logger.info(
            f"[contingency][{self.vehicle_id}] executor started "
            f"(timeout={self.heartbeat_timeout_s}s, "
            f"rungs={len(self.ladder)})"
        )
        try:
            while True:
                self.tick()
                time.sleep(tick_interval_s)
        except KeyboardInterrupt:
            logger.info(f"[contingency][{self.vehicle_id}] executor stopped")


# ---------------------------------------------------------------------------
# CLI entry point (for direct deployment: python -m harness.dispatch.contingency_executor)
# ---------------------------------------------------------------------------


def _cli() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="PX4 contingency ladder executor")
    parser.add_argument("ladder", help="Path to ladder YAML/JSON file")
    parser.add_argument("--vehicle-id", required=True)
    parser.add_argument("--mission-id", required=True)
    parser.add_argument("--heartbeat-timeout", type=float, default=5.0)
    parser.add_argument("--tick-interval", type=float, default=1.0)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    ladder = load_ladder(args.ladder)
    executor = ContingencyExecutor(
        vehicle_id=args.vehicle_id,
        mission_id=args.mission_id,
        ladder=ladder,
        heartbeat_timeout_s=args.heartbeat_timeout,
    )
    executor.run(tick_interval_s=args.tick_interval)


if __name__ == "__main__":
    _cli()
