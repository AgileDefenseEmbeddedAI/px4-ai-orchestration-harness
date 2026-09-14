"""
Deterministic plan validator engine.

Loads constraint families from config/constraints.yaml and checks every waypoint
and vehicle trajectory pair. Produces a structured verdict artifact matching
schemas/verdict.v1.json.

IMPORTANT: This module NEVER imports from harness.planner or any LLM client.
All decisions are pure deterministic logic. Shapely handles all geometry.
"""

import math
from typing import Optional

from shapely.geometry import Point, Polygon

from harness.api.models import MIG

VALIDATOR_VERSION = "1.0"

# MAV_CMD codes that are forbidden per vehicle class
_FORBIDDEN_CMDS: dict[str, set[str]] = {
    "rover": {
        "MAV_CMD_NAV_TAKEOFF",
        "MAV_CMD_NAV_LAND",
        "MAV_CMD_NAV_VTOL_TAKEOFF",
        "MAV_CMD_NAV_VTOL_LAND",
    },
    "multirotor": set(),
}


def run(mig: MIG, constraints: dict) -> dict:
    """
    Run all hard-constraint checks and return a verdict artifact.

    Args:
        mig: Mission Intent Graph to validate.
        constraints: Raw dict loaded from config/constraints.yaml.

    Returns:
        dict matching schemas/verdict.v1.json — reproducible given the same inputs.
    """
    violations: list[dict] = []
    wp_by_id = {wp.id: wp for wp in mig.waypoints}

    # Build waypoint → vehicle type mapping
    wp_to_types: dict[str, set[str]] = {}
    wp_to_vehicle: dict[str, str] = {}
    for vehicle in mig.vehicles:
        for wp_id in vehicle.waypoints:
            wp_to_types.setdefault(wp_id, set()).add(vehicle.vehicle_type.value)
            if wp_id not in wp_to_vehicle:
                wp_to_vehicle[wp_id] = vehicle.id

    # Extract constraint values from config (authoritative hard limits)
    max_alt_m: float = constraints.get("max_alt_m", 120.0)
    min_alt_m: float = constraints.get("min_alt_m", 5.0)
    require_rtl: bool = constraints.get("require_rtl", True)
    airspace_volumes: list = constraints.get("airspace_volumes", [])
    class_limits: dict = constraints.get("class_limits", {})
    min_h_sep_m: float = constraints.get("min_horizontal_sep_m", 50.0)
    min_v_sep_m: float = constraints.get("min_vertical_sep_m", 10.0)

    geofence = _build_geofence(constraints)

    # ----------------------------------------------------------------
    # 1. Vehicle presence
    # ----------------------------------------------------------------
    if not mig.vehicles:
        violations.append(_viol("VIOL-NO-VEHICLES", None, None,
                                "Mission has no vehicles assigned"))

    # ----------------------------------------------------------------
    # 2. Per-waypoint checks
    # ----------------------------------------------------------------
    for idx, wp in enumerate(mig.waypoints):
        veh_types = wp_to_types.get(wp.id, set())
        vehicle_id = wp_to_vehicle.get(wp.id)

        # Altitude ceiling (all aerial vehicles)
        if wp.alt_m > max_alt_m:
            violations.append(_viol(
                "VIOL-ALT-CEILING", vehicle_id, idx,
                f"Waypoint {wp.id} altitude {wp.alt_m}m exceeds ceiling {max_alt_m}m"
            ))

        # Altitude floor (multirotors only)
        if "multirotor" in veh_types and wp.alt_m < min_alt_m:
            violations.append(_viol(
                "VIOL-ALT-FLOOR", vehicle_id, idx,
                f"Waypoint {wp.id} altitude {wp.alt_m}m is below minimum {min_alt_m}m "
                f"for aerial vehicles"
            ))

        # Rover altitude — rovers must operate at ground level (alt_m == 0.0)
        if "rover" in veh_types and wp.alt_m != 0.0:
            violations.append(_viol(
                "VIOL-ROVER-ALT", vehicle_id, idx,
                f"Waypoint {wp.id} sets altitude {wp.alt_m}m for a rover vehicle "
                f"(must be 0.0)"
            ))

        # Geofence boundary
        if geofence is not None:
            pt = Point(wp.lon, wp.lat)
            if not geofence.contains(pt):
                violations.append(_viol(
                    "VIOL-GEOFENCE", vehicle_id, idx,
                    f"Waypoint {wp.id} at ({wp.lat}, {wp.lon}) is outside the geofence"
                ))

        # Restricted airspace volumes (cylinders)
        for vol in airspace_volumes:
            if _in_cylinder(wp, vol):
                violations.append(_viol(
                    "VIOL-AIRSPACE", vehicle_id, idx,
                    f"Waypoint {wp.id} at ({wp.lat}, {wp.lon}, {wp.alt_m}m) enters "
                    f"restricted airspace volume '{vol.get('name', 'unknown')}'"
                ))

        # Forbidden MAV_CMD for vehicle class
        if wp.mav_cmd:
            for vt in veh_types:
                forbidden = _FORBIDDEN_CMDS.get(vt, set())
                if wp.mav_cmd in forbidden:
                    violations.append(_viol(
                        "VIOL-FORBIDDEN-CMD", vehicle_id, idx,
                        f"Waypoint {wp.id} uses forbidden command {wp.mav_cmd} "
                        f"for vehicle class '{vt}'"
                    ))

    # ----------------------------------------------------------------
    # 3. Per-vehicle checks
    # ----------------------------------------------------------------
    for vehicle in mig.vehicles:
        vehicle_wps = [wp_by_id[wid] for wid in vehicle.waypoints if wid in wp_by_id]

        # Waypoint reference integrity
        all_wp_ids = {wp.id for wp in mig.waypoints}
        for wp_id in vehicle.waypoints:
            if wp_id not in all_wp_ids:
                violations.append(_viol(
                    "VIOL-UNKNOWN-WP", vehicle.id, None,
                    f"Vehicle {vehicle.id} references unknown waypoint '{wp_id}'"
                ))

        # RTL requirement
        if require_rtl:
            has_rtl = any(wp.role == "rtl" for wp in vehicle_wps)
            if not has_rtl:
                violations.append(_viol(
                    "VIOL-NO-RTL", vehicle.id, None,
                    f"Vehicle {vehicle.id} has no return-to-launch (RTL) waypoint"
                ))

        # Rover max speed (checked against class_limits in constraints.yaml)
        if vehicle.vehicle_type.value == "rover":
            rover_max_speed = class_limits.get("rover", {}).get("max_speed_ms", 5.0)
            speed = getattr(vehicle, "max_speed_ms", None)
            if speed is not None and speed > rover_max_speed:
                violations.append(_viol(
                    "VIOL-ROVER-SPEED", vehicle.id, None,
                    f"Vehicle {vehicle.id} max speed {speed}m/s exceeds rover limit "
                    f"{rover_max_speed}m/s"
                ))

        # Timing checks on waypoints with t_s set
        timed = [(i, wp) for i, wp in enumerate(vehicle_wps) if wp.t_s is not None]
        for k in range(len(timed) - 1):
            _, wp_a = timed[k]
            i_b, wp_b = timed[k + 1]
            if wp_b.t_s < wp_a.t_s:
                violations.append(_viol(
                    "VIOL-TIMESTAMP-ORDER", vehicle.id, i_b,
                    f"Waypoint {wp_b.id} timestamp {wp_b.t_s}s precedes "
                    f"{wp_a.id} timestamp {wp_a.t_s}s (out of order)"
                ))
            elif wp_b.t_s == wp_a.t_s:
                violations.append(_viol(
                    "VIOL-ZERO-DURATION", vehicle.id, i_b,
                    f"Zero-duration window between {wp_a.id} and {wp_b.id} "
                    f"(both at t={wp_a.t_s}s)"
                ))

    # ----------------------------------------------------------------
    # 4. Inter-vehicle deconfliction (timed waypoints only)
    # ----------------------------------------------------------------
    _check_deconfliction(mig, violations, min_h_sep_m, min_v_sep_m, wp_by_id)

    result = "accept" if not violations else "reject"
    return {
        "plan_id": mig.mission_id,
        "validator_version": VALIDATOR_VERSION,
        "result": result,
        "violations": violations,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _viol(
    constraint_id: str,
    vehicle_id: Optional[str],
    waypoint_index: Optional[int],
    description: str,
) -> dict:
    return {
        "constraint_id": constraint_id,
        "vehicle_id": vehicle_id,
        "waypoint_index": waypoint_index,
        "description": description,
    }


def _build_geofence(constraints: dict) -> Optional[Polygon]:
    coords = constraints.get("geofence_polygon", [])
    if not coords or len(coords) < 3:
        return None
    # constraints.yaml stores [lat, lon]; Shapely wants (x=lon, y=lat)
    return Polygon([(c[1], c[0]) for c in coords])


def _in_cylinder(wp, vol: dict) -> bool:
    """Return True if the waypoint falls inside the given cylinder volume."""
    floor_m: float = vol.get("floor_m", 0.0)
    ceiling_m: float = vol.get("ceiling_m", float("inf"))
    if not (floor_m <= wp.alt_m <= ceiling_m):
        return False
    center_lat: float = vol.get("center_lat", 0.0)
    center_lon: float = vol.get("center_lon", 0.0)
    radius_m: float = vol.get("radius_m", 0.0)
    return _haversine_m(wp.lat, wp.lon, center_lat, center_lon) <= radius_m


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _check_deconfliction(
    mig: MIG,
    violations: list,
    min_h_sep_m: float,
    min_v_sep_m: float,
    wp_by_id: dict,
) -> None:
    """Check all vehicle pairs for proximity violations at overlapping time windows."""
    vehicles = mig.vehicles
    for i in range(len(vehicles)):
        for j in range(i + 1, len(vehicles)):
            veh_a = vehicles[i]
            veh_b = vehicles[j]

            for idx_a, wp_id_a in enumerate(veh_a.waypoints):
                wp_a = wp_by_id.get(wp_id_a)
                if not wp_a or wp_a.t_s is None:
                    continue

                for idx_b, wp_id_b in enumerate(veh_b.waypoints):
                    wp_b = wp_by_id.get(wp_id_b)
                    if not wp_b or wp_b.t_s is None:
                        continue

                    # Only compare waypoints within a 30-second time window
                    if abs(wp_a.t_s - wp_b.t_s) > 30.0:
                        continue

                    h_dist = _haversine_m(wp_a.lat, wp_a.lon, wp_b.lat, wp_b.lon)
                    v_dist = abs(wp_a.alt_m - wp_b.alt_m)

                    if h_dist < min_h_sep_m and v_dist < min_v_sep_m:
                        violations.append(_viol(
                            "VIOL-DECONFLICT",
                            f"{veh_a.id},{veh_b.id}",
                            idx_a,
                            f"Vehicles {veh_a.id} and {veh_b.id} violate minimum "
                            f"separation at t={wp_a.t_s}s: "
                            f"horizontal {h_dist:.1f}m (min {min_h_sep_m}m), "
                            f"vertical {v_dist:.1f}m (min {min_v_sep_m}m)"
                        ))
