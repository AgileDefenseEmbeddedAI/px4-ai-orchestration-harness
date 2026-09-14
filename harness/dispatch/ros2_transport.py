"""
ROS 2 VAL transport — stub implementation.

Real implementation requires:
  - ROS 2 Humble environment with px4_msgs + px4_ros_com installed
  - uXRCE-DDS bridge running between the harness and the PX4 firmware
  - Topics: /fmu/in/trajectory_setpoint, /fmu/in/vehicle_command

This stub logs the dispatch without connecting to any hardware.
"""

import logging

from harness.api.models import MIG, VAL, Vehicle, VehicleAction, VehicleType

logger = logging.getLogger(__name__)


async def dispatch_val(val: VAL) -> dict:
    """
    Dispatch a Vehicle Action List over ROS 2 (uXRCE-DDS bridge to PX4).

    Returns a result dict describing what would have been sent.
    """
    logger.info(
        f"[ROS2] Dispatching VAL for vehicle {val.vehicle_id} "
        f"({val.vehicle_type}) — mission {val.mission_id}"
    )
    for i, action in enumerate(val.actions, 1):
        logger.info(f"[ROS2]   Action {i}: {action.action_type} -> {action.waypoint}")

    # Real implementation would publish to ROS 2 topics, e.g.:
    #   rclpy.init()
    #   node = rclpy.create_node("harness_dispatch")
    #   pub = node.create_publisher(TrajectorySetpoint, "/fmu/in/trajectory_setpoint", 10)
    #   for action in val.actions:
    #       msg = TrajectorySetpoint(...)
    #       pub.publish(msg)

    return {
        "transport": "ros2",
        "vehicle_id": val.vehicle_id,
        "vehicle_type": val.vehicle_type,
        "mission_id": val.mission_id,
        "status": "stub_dispatched",
        "action_count": len(val.actions),
        "cmd_sequence": [action.action_type for action in val.actions],
    }


def get_normalized_cmd_sequence(val: VAL) -> list[str]:
    """Return the action-type sequence dispatched for parity testing."""
    return [action.action_type for action in val.actions]


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
                    "lat": wp.lat,
                    "lon": wp.lon,
                    "alt_m": wp.alt_m,
                    "role": wp.role,
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
