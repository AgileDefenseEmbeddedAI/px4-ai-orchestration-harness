"""
Unit tests for the deterministic constraint checker.

All tests are synchronous — the validator never calls the LLM.
"""

import pytest

from harness.api.models import (
    Constraints,
    MIG,
    MissionStatus,
    Vehicle,
    VehicleType,
    Waypoint,
)
from harness.validator.constraint_checker import validate

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

GEOFENCE = [
    [35.1200, -79.0500],
    [35.1200, -78.9700],
    [35.1700, -78.9700],
    [35.1700, -79.0500],
]

CONSTRAINTS_CONFIG = {
    "geofence_polygon": GEOFENCE,
    "max_alt_m": 120.0,
    "min_alt_m": 5.0,
    "require_rtl": True,
}


def _base_mig(**overrides) -> MIG:
    """Return a minimal valid MIG, optionally overriding fields."""
    defaults = dict(
        version="1.0",
        mission_id="MSN-TEST0001",
        intent="Test mission",
        vehicles=[
            Vehicle(
                id="UAV-1",
                vehicle_type=VehicleType.multirotor,
                sitl_target="gz_x500",
                mavlink_sysid=1,
                waypoints=["WP-1", "WP-RTL"],
            )
        ],
        waypoints=[
            Waypoint(id="WP-1", lat=35.1490, lon=-79.0100, alt_m=50.0, role="survey"),
            Waypoint(id="WP-RTL", lat=35.1400, lon=-79.0110, alt_m=30.0, role="rtl"),
        ],
        constraints=Constraints(
            geofence_polygon=GEOFENCE,
            max_alt_m=120.0,
            min_alt_m=5.0,
            require_rtl=True,
            max_range_m=5000.0,
        ),
        status=MissionStatus.planning,
        validation_errors=[],
    )
    defaults.update(overrides)
    return MIG(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_valid_plan_passes():
    """A well-formed plan within all constraints should pass with no errors."""
    mig = _base_mig()
    is_valid, errors = validate(mig, CONSTRAINTS_CONFIG)
    assert is_valid is True
    assert errors == []


def test_altitude_too_high():
    """A waypoint above max_alt_m should produce a validation error."""
    mig = _base_mig(
        waypoints=[
            Waypoint(id="WP-1", lat=35.1490, lon=-79.0100, alt_m=999.0, role="survey"),
            Waypoint(id="WP-RTL", lat=35.1400, lon=-79.0110, alt_m=30.0, role="rtl"),
        ]
    )
    is_valid, errors = validate(mig, CONSTRAINTS_CONFIG)
    assert is_valid is False
    assert any("999" in e or "altitude" in e.lower() for e in errors)


def test_altitude_too_low_for_aerial():
    """A multirotor waypoint below min_alt_m should fail."""
    mig = _base_mig(
        waypoints=[
            Waypoint(id="WP-1", lat=35.1490, lon=-79.0100, alt_m=1.0, role="survey"),
            Waypoint(id="WP-RTL", lat=35.1400, lon=-79.0110, alt_m=30.0, role="rtl"),
        ]
    )
    is_valid, errors = validate(mig, CONSTRAINTS_CONFIG)
    assert is_valid is False
    assert any("1.0" in e or "below" in e.lower() or "minimum" in e.lower() for e in errors)


def test_rover_at_zero_alt_passes():
    """A rover waypoint at 0m altitude should NOT trigger the min_alt check."""
    mig = _base_mig(
        vehicles=[
            Vehicle(
                id="GND-1",
                vehicle_type=VehicleType.rover,
                sitl_target="gz_rover_ackermann",
                mavlink_sysid=1,
                waypoints=["WP-1", "WP-RTL"],
            )
        ],
        waypoints=[
            Waypoint(id="WP-1", lat=35.1490, lon=-79.0100, alt_m=0.0, role="survey"),
            Waypoint(id="WP-RTL", lat=35.1400, lon=-79.0110, alt_m=0.0, role="rtl"),
        ],
    )
    is_valid, errors = validate(mig, CONSTRAINTS_CONFIG)
    assert is_valid is True, f"Unexpected errors: {errors}"


def test_no_rtl_fails():
    """A vehicle without an RTL waypoint should fail when require_rtl is True."""
    mig = _base_mig(
        waypoints=[
            Waypoint(id="WP-1", lat=35.1490, lon=-79.0100, alt_m=50.0, role="survey"),
        ],
        vehicles=[
            Vehicle(
                id="UAV-1",
                vehicle_type=VehicleType.multirotor,
                sitl_target="gz_x500",
                mavlink_sysid=1,
                waypoints=["WP-1"],
            )
        ],
    )
    is_valid, errors = validate(mig, CONSTRAINTS_CONFIG)
    assert is_valid is False
    assert any("RTL" in e or "rtl" in e.lower() for e in errors)


def test_out_of_bounds_fails():
    """A waypoint outside the geofence polygon should fail."""
    mig = _base_mig(
        waypoints=[
            # New York City — far outside Fort Bragg geofence
            Waypoint(id="WP-1", lat=40.7128, lon=-74.0060, alt_m=50.0, role="survey"),
            Waypoint(id="WP-RTL", lat=40.7000, lon=-74.0000, alt_m=30.0, role="rtl"),
        ]
    )
    is_valid, errors = validate(mig, CONSTRAINTS_CONFIG)
    assert is_valid is False
    assert any("geofence" in e.lower() or "outside" in e.lower() for e in errors)


def test_empty_vehicles_fails():
    """A MIG with no vehicles should fail validation."""
    mig = _base_mig(vehicles=[], waypoints=[])
    is_valid, errors = validate(mig, CONSTRAINTS_CONFIG)
    assert is_valid is False
    assert any("vehicle" in e.lower() for e in errors)


def test_unknown_waypoint_reference_fails():
    """A vehicle referencing a non-existent waypoint ID should fail."""
    mig = _base_mig(
        vehicles=[
            Vehicle(
                id="UAV-1",
                vehicle_type=VehicleType.multirotor,
                sitl_target="gz_x500",
                mavlink_sysid=1,
                waypoints=["WP-1", "WP-MISSING", "WP-RTL"],
            )
        ],
    )
    is_valid, errors = validate(mig, CONSTRAINTS_CONFIG)
    assert is_valid is False
    assert any("WP-MISSING" in e for e in errors)


def test_no_geofence_config_skips_check():
    """When constraints_config has no geofence, no geofence errors are raised."""
    mig = _base_mig(
        waypoints=[
            Waypoint(id="WP-1", lat=40.7128, lon=-74.0060, alt_m=50.0, role="survey"),
            Waypoint(id="WP-RTL", lat=40.7000, lon=-74.0000, alt_m=30.0, role="rtl"),
        ]
    )
    is_valid, errors = validate(mig, {})  # No geofence in config
    # Should only fail on altitude (if applicable), not geofence
    assert not any("geofence" in e.lower() for e in errors)
