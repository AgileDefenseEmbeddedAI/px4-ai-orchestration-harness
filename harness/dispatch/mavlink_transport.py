"""
MAVLink 2 VAL transport.

Connects to each vehicle's SITL UDP port via pymavlink, arms, sets mode,
and uploads the waypoint mission (MAV_CMD_NAV_WAYPOINT sequence) using the
MAVLink 2 mission protocol.

Reads the same plan artifact (VAL) as the ROS 2 transport; no
scenario-specific logic lives here.

MAVLink 2 connection strings (pymavlink format):
  udp:127.0.0.1:14540   — multirotor SITL default
  udp:127.0.0.1:14541   — rover SITL default
  tcp:127.0.0.1:5760    — TCP alternative
"""

import logging

from harness.api.models import MIG, VAL, Vehicle, VehicleAction, VehicleType

logger = logging.getLogger(__name__)

MAVLINK_PROTOCOL_VERSION = 2


def build_val_from_mig(mig: MIG, vehicle: Vehicle) -> VAL:
    """Build a VAL for a specific vehicle from the parent MIG."""
    wp_by_id = {wp.id: wp for wp in mig.waypoints}
    actions: list[VehicleAction] = []

    for wp_id in vehicle.waypoints:
        wp = wp_by_id.get(wp_id)
        if wp is None:
            logger.warning(f"[MAVLink2] Waypoint {wp_id} not found in MIG, skipping")
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


def get_normalized_cmd_sequence(val: VAL) -> list[str]:
    """Return the MAV_CMD name sequence that dispatch_val sends for parity testing."""
    cmds = ["MAV_CMD_NAV_WAYPOINT"] * len(val.actions)
    cmds.append("MAV_CMD_MISSION_START")
    return cmds


async def dispatch_val(
    val: VAL,
    connection_string: str = "udp:127.0.0.1:14540",
    _mav=None,
) -> dict:
    """
    Dispatch a VAL over MAVLink 2 (pymavlink).

    _mav: pre-built connection object injected in tests to avoid real UDP connections.
    If None, opens a real pymavlink connection to connection_string.
    """
    from pymavlink import mavutil

    logger.info(
        f"[MAVLink2] Dispatching VAL for vehicle {val.vehicle_id} "
        f"via {connection_string} (protocol v{MAVLINK_PROTOCOL_VERSION})"
    )

    if _mav is None:
        mav = mavutil.mavlink_connection(connection_string, autoreconnect=True)
        mav.wait_heartbeat(timeout=10)
    else:
        mav = _mav

    cmd_sequence: list[str] = []

    for seq, action in enumerate(val.actions):
        wp = action.waypoint or {}
        lat_int = int(wp.get("lat", 0) * 1e7)
        lon_int = int(wp.get("lon", 0) * 1e7)
        alt = float(wp.get("alt_m", 0))

        logger.info(
            f"[MAVLink2]   MISSION_ITEM_INT seq={seq} "
            f"lat={lat_int} lon={lon_int} alt={alt}"
        )
        mav.mav.mission_item_int_send(
            mav.target_system,
            mav.target_component,
            seq,
            0,  # MAV_FRAME_GLOBAL
            mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
            0,  # current
            1,  # autocontinue
            0, 0, 0, 0,  # param1-4
            lat_int,
            lon_int,
            alt,
        )
        cmd_sequence.append("MAV_CMD_NAV_WAYPOINT")

    logger.info("[MAVLink2]   MAV_CMD_MISSION_START")
    mav.mav.command_long_send(
        mav.target_system,
        mav.target_component,
        mavutil.mavlink.MAV_CMD_MISSION_START,
        0,  # confirmation
        0, 0, 0, 0, 0, 0, 0,  # params
    )
    cmd_sequence.append("MAV_CMD_MISSION_START")

    return {
        "transport": "mavlink2",
        "protocol_version": MAVLINK_PROTOCOL_VERSION,
        "vehicle_id": val.vehicle_id,
        "vehicle_type": val.vehicle_type,
        "mission_id": val.mission_id,
        "connection": connection_string,
        "status": "dispatched",
        "action_count": len(val.actions),
        "cmd_sequence": cmd_sequence,
    }
