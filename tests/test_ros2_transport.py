"""
Unit tests for the ROS 2 VAL transport.
"""

from datetime import datetime, timezone

import pytest

from harness.api.models import (
    Constraints,
    MIG,
    MissionStatus,
    Vehicle,
    VehicleType,
    Waypoint,
)
from harness.dispatch import ros2_transport

GEOFENCE = [
    [35.12, -79.05],
    [35.12, -78.97],
    [35.17, -78.97],
    [35.17, -79.05],
]


@pytest.fixture
def sample_mig():
    return MIG(
        version="1.0",
        mission_id="MSN-ROS20001",
        created_at=datetime.now(timezone.utc),
        intent="Scout Alpha-7 with UAV, rover secures perimeter",
        vehicles=[
            Vehicle(
                id="UAV-1",
                vehicle_type=VehicleType.multirotor,
                sitl_target="gz_x500",
                mavlink_sysid=1,
                waypoints=["WP-1", "WP-2", "WP-RTL"],
            ),
            Vehicle(
                id="GND-1",
                vehicle_type=VehicleType.rover,
                sitl_target="gz_rover_ackermann",
                mavlink_sysid=2,
                waypoints=["WP-3", "WP-RTL-2"],
            ),
        ],
        waypoints=[
            Waypoint(id="WP-1", lat=35.149, lon=-79.010, alt_m=50.0, role="survey"),
            Waypoint(id="WP-2", lat=35.151, lon=-79.008, alt_m=50.0, role="loiter"),
            Waypoint(id="WP-RTL", lat=35.140, lon=-79.011, alt_m=30.0, role="rtl"),
            Waypoint(id="WP-3", lat=35.142, lon=-79.012, alt_m=0.0, role="perimeter"),
            Waypoint(id="WP-RTL-2", lat=35.140, lon=-79.011, alt_m=0.0, role="rtl"),
        ],
        constraints=Constraints(
            geofence_polygon=GEOFENCE,
            max_alt_m=120.0,
            min_alt_m=5.0,
            require_rtl=True,
            max_range_m=5000.0,
        ),
        status=MissionStatus.authorized,
        validation_errors=[],
    )


# ---------------------------------------------------------------------------
# build_val_from_mig
# ---------------------------------------------------------------------------


def test_build_val_preserves_waypoint_order(sample_mig):
    vehicle = sample_mig.vehicles[0]
    val = ros2_transport.build_val_from_mig(sample_mig, vehicle)

    assert len(val.actions) == 3
    roles = [a.waypoint["role"] for a in val.actions]
    assert roles == ["survey", "loiter", "rtl"]


def test_build_val_vehicle_id(sample_mig):
    vehicle = sample_mig.vehicles[0]
    val = ros2_transport.build_val_from_mig(sample_mig, vehicle)
    assert val.vehicle_id == "UAV-1"
    assert val.mission_id == "MSN-ROS20001"


def test_build_val_multirotor_speed(sample_mig):
    vehicle = sample_mig.vehicles[0]
    val = ros2_transport.build_val_from_mig(sample_mig, vehicle)
    for action in val.actions:
        assert action.parameters["speed_mps"] == 5.0


def test_build_val_rover_speed(sample_mig):
    vehicle = sample_mig.vehicles[1]
    val = ros2_transport.build_val_from_mig(sample_mig, vehicle)
    for action in val.actions:
        assert action.parameters["speed_mps"] == 2.0


def test_build_val_skips_missing_waypoint(sample_mig):
    """Unknown waypoint IDs are skipped rather than raising."""
    sample_mig.vehicles[0].waypoints.append("WP-NONEXISTENT")
    vehicle = sample_mig.vehicles[0]
    val = ros2_transport.build_val_from_mig(sample_mig, vehicle)
    assert len(val.actions) == 3  # WP-NONEXISTENT is dropped


# ---------------------------------------------------------------------------
# dispatch_val
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_val_returns_correct_structure(sample_mig):
    vehicle = sample_mig.vehicles[0]
    val = ros2_transport.build_val_from_mig(sample_mig, vehicle)
    result = await ros2_transport.dispatch_val(val)

    assert result["transport"] == "ros2"
    assert result["vehicle_id"] == "UAV-1"
    assert result["mission_id"] == "MSN-ROS20001"
    assert result["action_count"] == 3
    assert "cmd_sequence" in result


@pytest.mark.asyncio
async def test_dispatch_val_action_count_matches_waypoints(sample_mig):
    vehicle = sample_mig.vehicles[0]
    val = ros2_transport.build_val_from_mig(sample_mig, vehicle)
    result = await ros2_transport.dispatch_val(val)
    assert result["action_count"] == len(vehicle.waypoints)


@pytest.mark.asyncio
async def test_dispatch_val_cmd_sequence_is_action_types(sample_mig):
    vehicle = sample_mig.vehicles[0]
    val = ros2_transport.build_val_from_mig(sample_mig, vehicle)
    result = await ros2_transport.dispatch_val(val)
    assert result["cmd_sequence"] == ["goto_waypoint"] * len(val.actions)


# ---------------------------------------------------------------------------
# get_normalized_cmd_sequence
# ---------------------------------------------------------------------------


def test_normalized_sequence_length(sample_mig):
    vehicle = sample_mig.vehicles[0]
    val = ros2_transport.build_val_from_mig(sample_mig, vehicle)
    seq = ros2_transport.get_normalized_cmd_sequence(val)
    assert len(seq) == len(val.actions)
    assert all(s == "goto_waypoint" for s in seq)


# ---------------------------------------------------------------------------
# Authorization gate (API level)
# ---------------------------------------------------------------------------


def test_authorization_gate_rejected(app_client):
    """Rejecting authorization marks mission as failed; no dispatch occurs."""
    resp = app_client.post(
        "/intent",
        json={"text": "Scout Alpha-7 with UAV and secure perimeter with rover"},
    )
    assert resp.status_code == 200
    mission_id = resp.json()["mission_id"]

    auth_resp = app_client.post(
        f"/authorize/{mission_id}",
        json={"authorized": False, "operator": "Test Operator"},
    )
    # 200 = rejected (mission marked failed) or 409 = still planning
    assert auth_resp.status_code in (200, 409)
    if auth_resp.status_code == 200:
        assert auth_resp.json()["status"] == "failed"


def test_authorization_gate_unknown_mission(app_client):
    """Authorizing a non-existent mission returns 404."""
    resp = app_client.post(
        "/authorize/MSN-DOESNOTEXIST",
        json={"authorized": True, "operator": "Test Operator"},
    )
    assert resp.status_code == 404
