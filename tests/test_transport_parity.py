"""
Dual-transport mock parity tests.

Verifies that the ROS 2 and MAVLink 2 transports produce consistent results
for the same VAL: equal mission_id, vehicle_id, and action_count, with
transport-specific metadata differing as expected.
"""

import pytest

from harness.api.models import VAL, VehicleAction, VehicleType
from harness.dispatch import mavlink_transport, ros2_transport

_SAMPLE_VAL = VAL(
    mission_id="MSN-PARTEST1",
    vehicle_id="UAV-1",
    vehicle_type=VehicleType.multirotor,
    actions=[
        VehicleAction(
            action_type="goto_waypoint",
            waypoint={"lat": 35.1490, "lon": -79.0100, "alt_m": 50.0, "role": "survey"},
            parameters={"speed_mps": 5.0},
        ),
        VehicleAction(
            action_type="goto_waypoint",
            waypoint={"lat": 35.1400, "lon": -79.0110, "alt_m": 30.0, "role": "rtl"},
            parameters={"speed_mps": 5.0},
        ),
    ],
)


async def test_ros2_dispatch_returns_expected_fields():
    result = await ros2_transport.dispatch_val(_SAMPLE_VAL)
    assert result["transport"] == "ros2"
    assert result["mission_id"] == _SAMPLE_VAL.mission_id
    assert result["vehicle_id"] == _SAMPLE_VAL.vehicle_id
    assert result["action_count"] == len(_SAMPLE_VAL.actions)
    assert result["status"] == "stub_dispatched"


async def test_mavlink_dispatch_returns_expected_fields():
    result = await mavlink_transport.dispatch_val(_SAMPLE_VAL)
    assert result["transport"] == "mavlink2"
    assert result["mission_id"] == _SAMPLE_VAL.mission_id
    assert result["vehicle_id"] == _SAMPLE_VAL.vehicle_id
    assert result["action_count"] == len(_SAMPLE_VAL.actions)
    assert result["status"] == "stub_dispatched"


async def test_transport_parity_core_fields():
    """Both transports must report identical mission_id, vehicle_id, and action_count."""
    ros2_result = await ros2_transport.dispatch_val(_SAMPLE_VAL)
    mav_result = await mavlink_transport.dispatch_val(_SAMPLE_VAL)

    assert ros2_result["action_count"] == mav_result["action_count"]
    assert ros2_result["mission_id"] == mav_result["mission_id"]
    assert ros2_result["vehicle_id"] == mav_result["vehicle_id"]
    assert ros2_result["status"] == mav_result["status"]


async def test_transport_names_differ():
    """Transport-specific metadata must differ between the two transports."""
    ros2_result = await ros2_transport.dispatch_val(_SAMPLE_VAL)
    mav_result = await mavlink_transport.dispatch_val(_SAMPLE_VAL)
    assert ros2_result["transport"] != mav_result["transport"]


async def test_parity_with_build_val_from_mig(sample_mig):
    """build_val_from_mig produces a VAL that both transports dispatch identically."""
    uav = next(v for v in sample_mig.vehicles if v.vehicle_type == VehicleType.multirotor)
    val = ros2_transport.build_val_from_mig(sample_mig, uav)

    ros2_result = await ros2_transport.dispatch_val(val)
    mav_result = await mavlink_transport.dispatch_val(val)

    assert ros2_result["action_count"] == mav_result["action_count"]
    assert ros2_result["mission_id"] == mav_result["mission_id"]
    assert ros2_result["vehicle_id"] == mav_result["vehicle_id"]
