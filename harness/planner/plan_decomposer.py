"""
Deterministic plan decomposer.

Takes a MIG and expands vehicle-class semantic verbs (hover, loiter, traverse,
land, survey, perimeter, rtl) into PX4 MAV_CMD primitives appropriate for each
vehicle class (multirotor or rover).  Produces one Plan artifact per vehicle.

The decomposer NEVER calls the LLM.  It is pure, deterministic Python.
"""

from harness.api.models import MIG, MavCommand, Plan, VehicleType, Vehicle, Waypoint

# ---------------------------------------------------------------------------
# MAV_CMD constants (from MAVLink common message set)
# ---------------------------------------------------------------------------

MAV_CMD_NAV_WAYPOINT = 16
MAV_CMD_NAV_LOITER_UNLIM = 17
MAV_CMD_NAV_RETURN_TO_LAUNCH = 20
MAV_CMD_NAV_LAND = 21
MAV_CMD_NAV_TAKEOFF = 22

# Roles that map to loiter/hover for multirotors
_LOITER_ROLES = {"loiter", "hover"}
# Roles that trigger RTL
_RTL_ROLES = {"rtl"}
# Roles that trigger land (multirotor only)
_LAND_ROLES = {"land"}


def decompose(mig: MIG) -> list[Plan]:
    """Expand a MIG into one Plan per vehicle."""
    waypoint_index = {wp.id: wp for wp in mig.waypoints}
    return [
        _decompose_vehicle(vehicle, waypoint_index, mig.mission_id)
        for vehicle in mig.vehicles
    ]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _decompose_vehicle(
    vehicle: Vehicle,
    waypoint_index: dict[str, Waypoint],
    mission_id: str,
) -> Plan:
    commands: list[MavCommand] = []
    seq = 0

    for wp_id in vehicle.waypoints:
        wp = waypoint_index.get(wp_id)
        if wp is None:
            continue

        cmd = _role_to_command(wp, vehicle.vehicle_type, seq)
        commands.append(cmd)
        seq += 1

    return Plan(
        mission_id=mission_id,
        vehicle_id=vehicle.id,
        vehicle_type=vehicle.vehicle_type,
        commands=commands,
    )


def _role_to_command(
    wp: Waypoint,
    vehicle_type: VehicleType,
    seq: int,
) -> MavCommand:
    role = wp.role.lower()

    if role in _RTL_ROLES:
        return MavCommand(
            seq=seq,
            mav_cmd="MAV_CMD_NAV_RETURN_TO_LAUNCH",
            mav_cmd_id=MAV_CMD_NAV_RETURN_TO_LAUNCH,
            role=wp.role,
            lat=wp.lat,
            lon=wp.lon,
            alt_m=wp.alt_m if vehicle_type == VehicleType.multirotor else 0.0,
        )

    if vehicle_type == VehicleType.multirotor:
        return _multirotor_command(wp, role, seq)
    else:
        return _rover_command(wp, role, seq)


def _multirotor_command(wp: Waypoint, role: str, seq: int) -> MavCommand:
    if role in _LOITER_ROLES:
        return MavCommand(
            seq=seq,
            mav_cmd="MAV_CMD_NAV_LOITER_UNLIM",
            mav_cmd_id=MAV_CMD_NAV_LOITER_UNLIM,
            role=wp.role,
            lat=wp.lat,
            lon=wp.lon,
            alt_m=wp.alt_m,
            param3=0.0,  # radius (0 = point loiter)
        )

    if role in _LAND_ROLES:
        return MavCommand(
            seq=seq,
            mav_cmd="MAV_CMD_NAV_LAND",
            mav_cmd_id=MAV_CMD_NAV_LAND,
            role=wp.role,
            lat=wp.lat,
            lon=wp.lon,
            alt_m=0.0,
        )

    # Default: goto waypoint (survey, transit, perimeter, etc.)
    return MavCommand(
        seq=seq,
        mav_cmd="MAV_CMD_NAV_WAYPOINT",
        mav_cmd_id=MAV_CMD_NAV_WAYPOINT,
        role=wp.role,
        lat=wp.lat,
        lon=wp.lon,
        alt_m=wp.alt_m,
        param1=0.0,   # hold time (s)
        param2=5.0,   # acceptance radius (m)
    )


def _rover_command(wp: Waypoint, role: str, seq: int) -> MavCommand:
    # Rovers cannot loiter/hover or change altitude — all roles map to waypoint
    # except RTL (handled by the caller).
    return MavCommand(
        seq=seq,
        mav_cmd="MAV_CMD_NAV_WAYPOINT",
        mav_cmd_id=MAV_CMD_NAV_WAYPOINT,
        role=wp.role,
        lat=wp.lat,
        lon=wp.lon,
        alt_m=0.0,   # rovers stay on the ground
        param1=0.0,
        param2=2.0,  # tighter acceptance radius for ground vehicles
    )
