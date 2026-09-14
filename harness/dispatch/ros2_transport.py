"""
ROS 2 VAL transport — primary dispatch channel over uXRCE-DDS bridge.

Publishes VehicleCommand and TrajectorySetpoint messages on namespaced PX4
ROS 2 topics for each vehicle. Falls back to log-only mode when rclpy /
px4_msgs are unavailable (CI without ROS 2 installed).

Topic pattern:
  /{namespace}/fmu/in/vehicle_command
  /{namespace}/fmu/in/trajectory_setpoint
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from harness.api.models import MIG, VAL, Vehicle, VehicleAction, VehicleType

logger = logging.getLogger(__name__)

# MAVLink command IDs published in VehicleCommand messages
MAV_CMD_NAV_WAYPOINT          = 16
MAV_CMD_NAV_RETURN_TO_LAUNCH  = 20
MAV_CMD_COMPONENT_ARM_DISARM  = 400
MAV_CMD_NAV_TAKEOFF           = 22


class DispatchNotAuthorizedError(RuntimeError):
    """Raised when dispatch is attempted without a recorded authorization event."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _action_to_mav_cmd(action: VehicleAction, vehicle_type: VehicleType) -> int:  # noqa: ARG001
    """Map a VehicleAction role to the appropriate MAV_CMD integer."""
    role = (action.waypoint or {}).get("role", "survey")
    if role == "rtl":
        return MAV_CMD_NAV_RETURN_TO_LAUNCH
    return MAV_CMD_NAV_WAYPOINT


def _default_contingency_ladder(vehicle_type: VehicleType) -> list[dict]:
    """Return a default contingency ladder for the given vehicle class."""
    rtl_action = "loiter_then_land" if vehicle_type == VehicleType.multirotor else "stop_in_place"
    return [
        {"trigger": "link_loss_5s",    "action": "hold_position", "priority": 1},
        {"trigger": "link_loss_30s",   "action": rtl_action,      "priority": 2},
        {"trigger": "link_loss_120s",  "action": "emergency_land", "priority": 3},
        {"trigger": "battery_low",     "action": rtl_action,      "priority": 4},
        {"trigger": "battery_critical","action": "emergency_land", "priority": 5},
        {"trigger": "geofence_breach", "action": "rtl",           "priority": 6},
    ]


def _write_contingency_ladder(val: VAL, sitl_workdir: Optional[str] = None) -> Path:
    """
    Write the contingency ladder JSON to the vehicle's companion channel.
    Simulates the side-channel file drop to the SITL working directory.
    """
    ladder = val.contingency_ladder or _default_contingency_ladder(val.vehicle_type)
    base = Path(sitl_workdir or "missions/contingency")
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{val.vehicle_id}_contingency_ladder.json"
    with path.open("w") as fh:
        json.dump(
            {
                "mission_id": val.mission_id,
                "vehicle_id": val.vehicle_id,
                "vehicle_type": val.vehicle_type,
                "ladder": ladder,
            },
            fh,
            indent=2,
        )
    logger.info(f"[ROS2] Contingency ladder written to {path}")
    return path


def _ros2_publish(val: VAL, namespace: str) -> dict:
    """
    Publish VehicleCommand (+ TrajectorySetpoint for multirotors) via rclpy.

    Uses lazy imports so the module is importable in CI without ROS 2 installed.
    Raises ImportError if rclpy / px4_msgs are not available.
    """
    import rclpy  # noqa: PLC0415 — intentional lazy import; CI mocks via sys.modules
    from px4_msgs.msg import TrajectorySetpoint, VehicleCommand  # noqa: PLC0415

    if not rclpy.ok():
        rclpy.init()

    node_name = f"harness_dispatch_{val.vehicle_id.lower().replace('-', '_')}"
    node = rclpy.create_node(node_name)

    cmd_topic  = f"{namespace}/fmu/in/vehicle_command"
    traj_topic = f"{namespace}/fmu/in/trajectory_setpoint"

    cmd_pub  = node.create_publisher(VehicleCommand,      cmd_topic,  10)
    traj_pub = node.create_publisher(TrajectorySetpoint,  traj_topic, 10)

    published_cmds: list[dict] = []
    for action in val.actions:
        mav_cmd = _action_to_mav_cmd(action, val.vehicle_type)
        wp = action.waypoint or {}

        cmd_msg = VehicleCommand()
        cmd_msg.command          = mav_cmd
        cmd_msg.param1           = 0.0
        cmd_msg.param5           = float(wp.get("lat", 0.0))
        cmd_msg.param6           = float(wp.get("lon", 0.0))
        cmd_msg.param7           = (
            float(wp.get("alt_m", 0.0))
            if val.vehicle_type == VehicleType.multirotor
            else 0.0
        )
        cmd_msg.target_system    = 1
        cmd_msg.target_component = 1
        cmd_pub.publish(cmd_msg)

        if val.vehicle_type == VehicleType.multirotor:
            traj_msg = TrajectorySetpoint()
            # NED convention: altitude is negative-down
            traj_msg.position = [
                float(wp.get("lat", 0.0)),
                float(wp.get("lon", 0.0)),
                -float(wp.get("alt_m", 0.0)),
            ]
            traj_msg.yaw = float("nan")
            traj_pub.publish(traj_msg)

        published_cmds.append(
            {
                "command":     mav_cmd,
                "role":        wp.get("role", ""),
                "action_type": action.action_type,
            }
        )

    node.destroy_node()
    return {"published": published_cmds, "namespace": namespace}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def dispatch_val(
    val: VAL,
    *,
    mission_id: str = "",
    namespace: str = "",
    authorized: bool = False,
    sitl_workdir: Optional[str] = None,
) -> dict:
    """
    Dispatch a Vehicle Action List over the ROS 2 uXRCE-DDS bridge.

    Parameters
    ----------
    val:          Vehicle Action List to dispatch.
    mission_id:   Mission identifier (for logging / error messages).
    namespace:    ROS 2 topic namespace, e.g. ``/px4_1``.
    authorized:   Must be True — set by the authorization gate in routes.py.
                  Passing False raises DispatchNotAuthorizedError (defense-in-depth).
    sitl_workdir: Directory for contingency-ladder file drops.
                  Defaults to ``missions/contingency``.
    """
    if not authorized:
        raise DispatchNotAuthorizedError(
            f"Mission {mission_id or val.mission_id}: dispatch blocked — "
            "authorization event has not been recorded"
        )

    logger.info(
        f"[ROS2] Dispatching VAL for {val.vehicle_id} ({val.vehicle_type}) "
        f"— mission {val.mission_id}  ns={namespace!r}"
    )
    for i, action in enumerate(val.actions, 1):
        logger.info(f"[ROS2]   Action {i}: {action.action_type} -> {action.waypoint}")

    # Write contingency ladder before issuing commands (audit-before-dispatch rule)
    ladder_path = _write_contingency_ladder(val, sitl_workdir)

    try:
        ros2_result = _ros2_publish(val, namespace)
        transport_mode = "ros2_live"
    except ImportError:
        logger.warning("[ROS2] rclpy/px4_msgs not available — log-only mode")
        ros2_result = {
            "published": [
                {
                    "command":     _action_to_mav_cmd(a, val.vehicle_type),
                    "role":        (a.waypoint or {}).get("role", ""),
                    "action_type": a.action_type,
                }
                for a in val.actions
            ],
            "namespace": namespace,
        }
        transport_mode = "log_only"

    return {
        "transport":               "ros2",
        "mode":                    transport_mode,
        "vehicle_id":              val.vehicle_id,
        "vehicle_type":            val.vehicle_type,
        "mission_id":              val.mission_id,
        "namespace":               namespace,
        "action_count":            len(val.actions),
        "contingency_ladder_path": str(ladder_path),
        "ros2":                    ros2_result,
    }


def build_val_from_mig(mig: MIG, vehicle: Vehicle) -> VAL:
    """Build a VAL for a specific vehicle from the parent MIG."""
    wp_by_id = {wp.id: wp for wp in mig.waypoints}
    actions: list[VehicleAction] = []

    for wp_id in vehicle.waypoints:
        wp = wp_by_id.get(wp_id)
        if wp is None:
            logger.warning(f"[ROS2] Waypoint {wp_id} not found in MIG, skipping")
            continue
        speed = 5.0 if vehicle.vehicle_type == VehicleType.multirotor else 2.0
        actions.append(
            VehicleAction(
                action_type="goto_waypoint",
                waypoint={
                    "lat":   wp.lat,
                    "lon":   wp.lon,
                    "alt_m": wp.alt_m,
                    "role":  wp.role,
                },
                parameters={"speed_mps": speed},
            )
        )

    return VAL(
        mission_id=mig.mission_id,
        vehicle_id=vehicle.id,
        vehicle_type=vehicle.vehicle_type,
        actions=actions,
    )
