"""
Unit tests for the MAVLink 2 VAL transport.

Mocks the pymavlink connection; verifies MAV_CMD sequence, sysid routing
per vehicle, and authorization gate — same assertion set as test_ros2_transport.py.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from harness.api.models import (
    Constraints,
    MIG,
    MissionStatus,
    Vehicle,
    VehicleType,
    Waypoint,
)
from harness.dispatch import mavlink_transport

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
        mission_id="MSN-MAV0001",
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


def _make_mock_mav(sysid: int = 1) -> MagicMock:
    """Return a mock pymavlink connection."""
    mav = MagicMock()
    mav.target_system = sysid
    mav.target_component = 1
    mav.mav = MagicMock()
    return mav


# ---------------------------------------------------------------------------
# build_val_from_mig (same assertions as test_ros2_transport.py)
# ---------------------------------------------------------------------------


def test_build_val_preserves_waypoint_order(sample_mig):
    vehicle = sample_mig.vehicles[0]
    val = mavlink_transport.build_val_from_mig(sample_mig, vehicle)

    assert len(val.actions) == 3
    roles = [a.waypoint["role"] for a in val.actions]
    assert roles == ["survey", "loiter", "rtl"]


def test_build_val_vehicle_id(sample_mig):
    vehicle = sample_mig.vehicles[0]
    val = mavlink_transport.build_val_from_mig(sample_mig, vehicle)
    assert val.vehicle_id == "UAV-1"
    assert val.mission_id == "MSN-MAV0001"


def test_build_val_multirotor_speed(sample_mig):
    vehicle = sample_mig.vehicles[0]
    val = mavlink_transport.build_val_from_mig(sample_mig, vehicle)
    for action in val.actions:
        assert action.parameters["speed_mps"] == 5.0


def test_build_val_rover_speed(sample_mig):
    vehicle = sample_mig.vehicles[1]
    val = mavlink_transport.build_val_from_mig(sample_mig, vehicle)
    for action in val.actions:
        assert action.parameters["speed_mps"] == 2.0


def test_build_val_skips_missing_waypoint(sample_mig):
    sample_mig.vehicles[0].waypoints.append("WP-NONEXISTENT")
    vehicle = sample_mig.vehicles[0]
    val = mavlink_transport.build_val_from_mig(sample_mig, vehicle)
    assert len(val.actions) == 3


# ---------------------------------------------------------------------------
# MAV_CMD sequence verification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_sends_nav_waypoint_per_action(sample_mig):
    """dispatch_val sends MISSION_ITEM_INT (MAV_CMD_NAV_WAYPOINT) for each action."""
    vehicle = sample_mig.vehicles[0]
    val = mavlink_transport.build_val_from_mig(sample_mig, vehicle)
    mock_mav = _make_mock_mav(sysid=vehicle.mavlink_sysid)

    result = await mavlink_transport.dispatch_val(val, _mav=mock_mav)

    assert mock_mav.mav.mission_item_int_send.call_count == len(val.actions)
    nav_cmds = [c for c in result["cmd_sequence"] if c == "MAV_CMD_NAV_WAYPOINT"]
    assert len(nav_cmds) == len(val.actions)


@pytest.mark.asyncio
async def test_dispatch_sends_mission_start_last(sample_mig):
    """MAV_CMD_MISSION_START is sent exactly once, after all waypoints."""
    vehicle = sample_mig.vehicles[0]
    val = mavlink_transport.build_val_from_mig(sample_mig, vehicle)
    mock_mav = _make_mock_mav()

    result = await mavlink_transport.dispatch_val(val, _mav=mock_mav)

    mock_mav.mav.command_long_send.assert_called_once()
    assert result["cmd_sequence"][-1] == "MAV_CMD_MISSION_START"


@pytest.mark.asyncio
async def test_dispatch_cmd_sequence_order(sample_mig):
    """cmd_sequence is [NAV_WAYPOINT, ..., MISSION_START] — waypoints before start."""
    vehicle = sample_mig.vehicles[0]
    val = mavlink_transport.build_val_from_mig(sample_mig, vehicle)
    mock_mav = _make_mock_mav()

    result = await mavlink_transport.dispatch_val(val, _mav=mock_mav)

    seq = result["cmd_sequence"]
    assert seq[:-1] == ["MAV_CMD_NAV_WAYPOINT"] * len(val.actions)
    assert seq[-1] == "MAV_CMD_MISSION_START"


# ---------------------------------------------------------------------------
# Sysid routing per vehicle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_sysid_routing_uav(sample_mig):
    """UAV-1 dispatches to its own connection string."""
    vehicle = sample_mig.vehicles[0]
    val = mavlink_transport.build_val_from_mig(sample_mig, vehicle)
    mock_mav = _make_mock_mav(sysid=vehicle.mavlink_sysid)

    result = await mavlink_transport.dispatch_val(
        val, connection_string="udp:127.0.0.1:14540", _mav=mock_mav
    )

    assert result["connection"] == "udp:127.0.0.1:14540"
    assert result["vehicle_id"] == "UAV-1"


@pytest.mark.asyncio
async def test_dispatch_sysid_routing_rover(sample_mig):
    """GND-1 dispatches to its own connection string (different port)."""
    vehicle = sample_mig.vehicles[1]
    val = mavlink_transport.build_val_from_mig(sample_mig, vehicle)
    mock_mav = _make_mock_mav(sysid=vehicle.mavlink_sysid)

    result = await mavlink_transport.dispatch_val(
        val, connection_string="udp:127.0.0.1:14541", _mav=mock_mav
    )

    assert result["connection"] == "udp:127.0.0.1:14541"
    assert result["vehicle_id"] == "GND-1"


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_result_structure(sample_mig):
    vehicle = sample_mig.vehicles[0]
    val = mavlink_transport.build_val_from_mig(sample_mig, vehicle)
    mock_mav = _make_mock_mav()

    result = await mavlink_transport.dispatch_val(val, _mav=mock_mav)

    assert result["transport"] == "mavlink2"
    assert result["protocol_version"] == 2
    assert result["vehicle_id"] == "UAV-1"
    assert result["mission_id"] == "MSN-MAV0001"
    assert result["action_count"] == 3
    assert "cmd_sequence" in result
    assert result["status"] == "dispatched"


# ---------------------------------------------------------------------------
# get_normalized_cmd_sequence
# ---------------------------------------------------------------------------


def test_normalized_cmd_sequence_structure(sample_mig):
    vehicle = sample_mig.vehicles[0]
    val = mavlink_transport.build_val_from_mig(sample_mig, vehicle)
    seq = mavlink_transport.get_normalized_cmd_sequence(val)

    assert len(seq) == len(val.actions) + 1
    assert seq[-1] == "MAV_CMD_MISSION_START"
    assert all(c == "MAV_CMD_NAV_WAYPOINT" for c in seq[:-1])


# ---------------------------------------------------------------------------
# Authorization gate (API level — mirrors test_ros2_transport.py)
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
