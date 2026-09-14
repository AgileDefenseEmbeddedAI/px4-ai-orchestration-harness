"""
pytest fixtures shared across the test suite.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from harness.api.main import app
from harness.api.models import (
    Constraints,
    MIG,
    MissionStatus,
    Vehicle,
    VehicleType,
    Waypoint,
)

# ---------------------------------------------------------------------------
# Shared constraints config (matches config/constraints.yaml)
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
    "max_range_m": 5000.0,
}


# ---------------------------------------------------------------------------
# FastAPI test client fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def app_client():
    """TestClient with pre-configured app state (no real config files needed)."""
    with TestClient(app) as client:
        # Override state set by lifespan with test-safe values
        app.state.config = {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": None,
            "api_key": "sk-test-placeholder",
        }
        app.state.constraints_config = CONSTRAINTS_CONFIG
        app.state.vehicles_config = {
            "fleet": [
                {
                    "id": "UAV-1",
                    "vehicle_type": "multirotor",
                    "mavlink_connection": "udp:127.0.0.1:14540",
                },
                {
                    "id": "GND-1",
                    "vehicle_type": "rover",
                    "mavlink_connection": "udp:127.0.0.1:14541",
                },
            ]
        }
        app.state.missions = {}
        yield client


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_intent() -> str:
    return (
        "Scout grid reference Alpha-7 with UAV, "
        "then have rover secure the perimeter and return to base"
    )


@pytest.fixture
def sample_mig() -> MIG:
    """A valid MIG with two vehicles and six waypoints (within the test geofence)."""
    return MIG(
        version="1.0",
        mission_id="MSN-TESTTEST",
        created_at=datetime.now(timezone.utc),
        intent="Scout Alpha-7 with UAV and secure perimeter with rover",
        vehicles=[
            Vehicle(
                id="UAV-1",
                vehicle_type=VehicleType.multirotor,
                sitl_target="gz_x500",
                mavlink_sysid=1,
                waypoints=["WP-1", "WP-2", "WP-RTL-1"],
            ),
            Vehicle(
                id="GND-1",
                vehicle_type=VehicleType.rover,
                sitl_target="gz_rover_ackermann",
                mavlink_sysid=2,
                waypoints=["WP-3", "WP-4", "WP-RTL-2"],
            ),
        ],
        waypoints=[
            Waypoint(id="WP-1",    lat=35.1490, lon=-79.0100, alt_m=50.0, role="survey"),
            Waypoint(id="WP-2",    lat=35.1510, lon=-79.0080, alt_m=50.0, role="loiter"),
            Waypoint(id="WP-RTL-1",lat=35.1400, lon=-79.0110, alt_m=30.0, role="rtl"),
            Waypoint(id="WP-3",    lat=35.1420, lon=-79.0120, alt_m=0.0,  role="survey"),
            Waypoint(id="WP-4",    lat=35.1430, lon=-79.0090, alt_m=0.0,  role="perimeter"),
            Waypoint(id="WP-RTL-2",lat=35.1400, lon=-79.0110, alt_m=0.0,  role="rtl"),
        ],
        constraints=Constraints(
            geofence_polygon=GEOFENCE,
            max_alt_m=120.0,
            min_alt_m=5.0,
            require_rtl=True,
            max_range_m=5000.0,
        ),
        status=MissionStatus.pending_authorization,
        validation_errors=[],
    )
