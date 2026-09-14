"""
MAVLink 2 VAL transport — stub implementation.

Real implementation requires SITL instances running and pymavlink 2.x.

MAVLink 2 connection strings (pymavlink format):
  udp:127.0.0.1:14540   — multirotor SITL default
  udp:127.0.0.1:14541   — rover SITL default
  tcp:127.0.0.1:5760    — TCP alternative

Real dispatch sequence:
  1. mav = mavutil.mavlink_connection(connection_string)
  2. mav.wait_heartbeat()
  3. Upload MISSION_ITEM_INT messages for each waypoint
  4. Send MAV_CMD_MISSION_START via command_long_send
"""

import logging

from harness.api.models import VAL

logger = logging.getLogger(__name__)

MAVLINK_PROTOCOL_VERSION = 2


async def dispatch_val(
    val: VAL,
    connection_string: str = "udp:127.0.0.1:14540",
) -> dict:
    """
    Dispatch a Vehicle Action List over MAVLink 2 (pymavlink).

    Returns a result dict describing what would have been sent.
    """
    logger.info(
        f"[MAVLink2] Dispatching VAL for vehicle {val.vehicle_id} "
        f"via {connection_string} (protocol v{MAVLINK_PROTOCOL_VERSION})"
    )
    logger.info(f"[MAVLink2] {len(val.actions)} actions for mission {val.mission_id}")
    for i, action in enumerate(val.actions, 1):
        logger.info(f"[MAVLink2]   Action {i}: {action.action_type} -> {action.waypoint}")

    # Real implementation (pymavlink):
    #   from pymavlink import mavutil
    #   mav = mavutil.mavlink_connection(connection_string, autoreconnect=True)
    #   mav.wait_heartbeat(timeout=10)
    #   for seq, action in enumerate(val.actions):
    #       wp = action.waypoint
    #       mav.mav.mission_item_int_send(
    #           mav.target_system, mav.target_component,
    #           seq, 0,  # frame=MAV_FRAME_GLOBAL
    #           mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
    #           0, 1, 0, 0, 0, 0,
    #           int(wp["lat"] * 1e7), int(wp["lon"] * 1e7), wp["alt_m"]
    #       )
    #   mav.mav.command_long_send(
    #       mav.target_system, mav.target_component,
    #       mavutil.mavlink.MAV_CMD_MISSION_START, 0, 0, 0, 0, 0, 0, 0, 0
    #   )

    return {
        "transport": "mavlink2",
        "protocol_version": MAVLINK_PROTOCOL_VERSION,
        "vehicle_id": val.vehicle_id,
        "mission_id": val.mission_id,
        "connection": connection_string,
        "status": "stub_dispatched",
        "action_count": len(val.actions),
    }
