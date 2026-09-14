"""
Deterministic plan validator.

Checks a MIG against hard constraints using Shapely for geofence geometry.
This module NEVER calls the LLM — all decisions are pure deterministic logic.
"""

import logging

from shapely.geometry import Point, Polygon

from harness.api.models import MIG, VehicleType

logger = logging.getLogger(__name__)


def validate(mig: MIG, constraints_config: dict) -> tuple[bool, list[str]]:
    """
    Run all hard-constraint checks against a MIG.

    Args:
        mig: The Mission Intent Graph to validate.
        constraints_config: Raw dict from config/constraints.yaml (provides geofence,
            etc. that override or supplement MIG-level constraints).

    Returns:
        (is_valid, errors) — is_valid is True only when errors is empty.
    """
    errors: list[str] = []

    # Build a reverse map: waypoint_id -> list[Vehicle] that reference it
    wp_to_vehicles: dict[str, list] = {}
    for vehicle in mig.vehicles:
        for wp_id in vehicle.waypoints:
            wp_to_vehicles.setdefault(wp_id, []).append(vehicle)

    # ------------------------------------------------------------------
    # 1. Vehicle presence check
    # ------------------------------------------------------------------
    if len(mig.vehicles) == 0:
        errors.append("Mission has no vehicles assigned")

    # ------------------------------------------------------------------
    # 2. Altitude bounds
    # ------------------------------------------------------------------
    for wp in mig.waypoints:
        if wp.alt_m > mig.constraints.max_alt_m:
            errors.append(
                f"Waypoint {wp.id} altitude {wp.alt_m}m exceeds maximum "
                f"{mig.constraints.max_alt_m}m"
            )

        # min_alt applies only to aerial (multirotor) vehicles
        vehicles_for_wp = wp_to_vehicles.get(wp.id, [])
        has_aerial = any(v.vehicle_type == VehicleType.multirotor for v in vehicles_for_wp)
        if has_aerial and wp.alt_m < mig.constraints.min_alt_m:
            errors.append(
                f"Waypoint {wp.id} altitude {wp.alt_m}m is below the minimum "
                f"{mig.constraints.min_alt_m}m required for aerial vehicles"
            )

    # ------------------------------------------------------------------
    # 3. RTL requirement
    # ------------------------------------------------------------------
    if mig.constraints.require_rtl:
        wp_by_id = {wp.id: wp for wp in mig.waypoints}
        for vehicle in mig.vehicles:
            vehicle_wps = [wp_by_id[wid] for wid in vehicle.waypoints if wid in wp_by_id]
            has_rtl = any(wp.role == "rtl" for wp in vehicle_wps)
            if not has_rtl:
                errors.append(
                    f"Vehicle {vehicle.id} has no RTL waypoint (require_rtl is true)"
                )

    # ------------------------------------------------------------------
    # 4. Geofence check (coordinates come from constraints_config, not LLM)
    # ------------------------------------------------------------------
    geofence_coords = constraints_config.get("geofence_polygon", [])
    if geofence_coords and len(geofence_coords) >= 3:
        # constraints.yaml stores [lat, lon]; Shapely wants (x, y) = (lon, lat)
        geofence = Polygon([(c[1], c[0]) for c in geofence_coords])
        for wp in mig.waypoints:
            point = Point(wp.lon, wp.lat)
            if not geofence.contains(point):
                errors.append(
                    f"Waypoint {wp.id} at ({wp.lat}, {wp.lon}) is outside the geofence"
                )

    # ------------------------------------------------------------------
    # 5. Waypoint reference integrity
    # ------------------------------------------------------------------
    all_wp_ids = {wp.id for wp in mig.waypoints}
    for vehicle in mig.vehicles:
        for wp_id in vehicle.waypoints:
            if wp_id not in all_wp_ids:
                errors.append(
                    f"Vehicle {vehicle.id} references unknown waypoint '{wp_id}'"
                )

    is_valid = len(errors) == 0
    if is_valid:
        logger.info(f"[validator] MIG {mig.mission_id} passed all constraint checks")
    else:
        logger.warning(
            f"[validator] MIG {mig.mission_id} failed validation with "
            f"{len(errors)} error(s): {errors}"
        )
    return is_valid, errors
