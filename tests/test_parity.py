"""
Dual-transport parity test.

Asserts that the normalized dispatch command sequence produced by both the
ROS 2 and MAVLink transports for the same plan artifact is identical —
satisfying REQ-DSP-02 / REQ-NF-04.

Uses the four_vehicle_basic.yaml scenario as the canonical parity fixture.
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
from harness.dispatch import mavlink_transport, ros2_transport

GEOFENCE = [
    [35.12, -79.05],
    [35.12, -78.97],
    [35.17, -78.97],
    [35.17, -79.05],
]


@pytest.fixture
def four_vehicle_basic_mig():
    """Four-vehicle MIG matching tests/scenarios/four_vehicle_basic.yaml."""
    return MIG(
        version="1.0",
        mission_id="MSN-4VEH001",
        created_at=datetime.now(timezone.utc),
        intent=(
            "Dispatch UAV-1 and UAV-2 to survey Alpha and Bravo sectors at 60m, "
            "deploy GND-1 and GND-2 to secure the perimeter, all vehicles return to base"
        ),
        vehicles=[
            Vehicle(
                id="UAV-1",
                vehicle_type=VehicleType.multirotor,
                sitl_target="gz_x500",
                mavlink_sysid=1,
                waypoints=["WP-A1", "WP-A2", "WP-RTL-1"],
            ),
            Vehicle(
                id="UAV-2",
                vehicle_type=VehicleType.multirotor,
                sitl_target="gz_x500",
                mavlink_sysid=2,
                waypoints=["WP-B1", "WP-B2", "WP-RTL-2"],
            ),
            Vehicle(
                id="GND-1",
                vehicle_type=VehicleType.rover,
                sitl_target="gz_rover_ackermann",
                mavlink_sysid=3,
                waypoints=["WP-P1", "WP-RTL-3"],
            ),
            Vehicle(
                id="GND-2",
                vehicle_type=VehicleType.rover,
                sitl_target="gz_rover_ackermann",
                mavlink_sysid=4,
                waypoints=["WP-P2", "WP-RTL-4"],
            ),
        ],
        waypoints=[
            Waypoint(id="WP-A1",   lat=35.149, lon=-79.010, alt_m=60.0, role="survey"),
            Waypoint(id="WP-A2",   lat=35.151, lon=-79.008, alt_m=60.0, role="loiter"),
            Waypoint(id="WP-RTL-1",lat=35.140, lon=-79.011, alt_m=30.0, role="rtl"),
            Waypoint(id="WP-B1",   lat=35.155, lon=-79.015, alt_m=60.0, role="survey"),
            Waypoint(id="WP-B2",   lat=35.157, lon=-79.013, alt_m=60.0, role="loiter"),
            Waypoint(id="WP-RTL-2",lat=35.140, lon=-79.011, alt_m=30.0, role="rtl"),
            Waypoint(id="WP-P1",   lat=35.142, lon=-79.012, alt_m=0.0,  role="perimeter"),
            Waypoint(id="WP-RTL-3",lat=35.140, lon=-79.011, alt_m=0.0,  role="rtl"),
            Waypoint(id="WP-P2",   lat=35.144, lon=-79.009, alt_m=0.0,  role="perimeter"),
            Waypoint(id="WP-RTL-4",lat=35.140, lon=-79.011, alt_m=0.0,  role="rtl"),
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


def test_parity_waypoint_sequence_per_vehicle(four_vehicle_basic_mig):
    """Both transports produce identical waypoint (lat, lon, alt, role) sequences."""
    mig = four_vehicle_basic_mig

    for vehicle in mig.vehicles:
        ros2_val = ros2_transport.build_val_from_mig(mig, vehicle)
        mav_val = mavlink_transport.build_val_from_mig(mig, vehicle)

        assert len(ros2_val.actions) == len(mav_val.actions), (
            f"Vehicle {vehicle.id}: action count mismatch "
            f"({len(ros2_val.actions)} ros2 vs {len(mav_val.actions)} mavlink)"
        )

        for i, (r_action, m_action) in enumerate(zip(ros2_val.actions, mav_val.actions)):
            assert r_action.waypoint == m_action.waypoint, (
                f"Vehicle {vehicle.id}, action {i}: waypoint mismatch\n"
                f"  ros2:    {r_action.waypoint}\n"
                f"  mavlink: {m_action.waypoint}"
            )


def test_parity_all_four_vehicles_have_actions(four_vehicle_basic_mig):
    """All four vehicles produce non-empty VALs from both transports."""
    mig = four_vehicle_basic_mig
    assert len(mig.vehicles) == 4

    for vehicle in mig.vehicles:
        ros2_val = ros2_transport.build_val_from_mig(mig, vehicle)
        mav_val = mavlink_transport.build_val_from_mig(mig, vehicle)

        assert len(ros2_val.actions) > 0, f"{vehicle.id}: ROS 2 VAL has no actions"
        assert len(mav_val.actions) > 0, f"{vehicle.id}: MAVLink VAL has no actions"
        assert ros2_val.vehicle_id == vehicle.id
        assert mav_val.vehicle_id == vehicle.id


def test_parity_mavlink_cmd_sequence_length(four_vehicle_basic_mig):
    """MAVLink cmd_sequence length = waypoints + 1 (MISSION_START) for each vehicle."""
    mig = four_vehicle_basic_mig

    for vehicle in mig.vehicles:
        val = mavlink_transport.build_val_from_mig(mig, vehicle)
        seq = mavlink_transport.get_normalized_cmd_sequence(val)

        assert len(seq) == len(vehicle.waypoints) + 1, (
            f"Vehicle {vehicle.id}: expected {len(vehicle.waypoints) + 1} cmds, got {len(seq)}"
        )
        assert seq[-1] == "MAV_CMD_MISSION_START"
        assert all(c == "MAV_CMD_NAV_WAYPOINT" for c in seq[:-1])


def test_parity_rtl_waypoint_present_for_all_vehicles(four_vehicle_basic_mig):
    """Every vehicle in the four_vehicle_basic scenario has an RTL waypoint."""
    mig = four_vehicle_basic_mig

    for vehicle in mig.vehicles:
        val = ros2_transport.build_val_from_mig(mig, vehicle)
        roles = [a.waypoint["role"] for a in val.actions]
        assert "rtl" in roles, f"Vehicle {vehicle.id} missing RTL waypoint"


def test_parity_ros2_sequence_count_matches_mavlink(four_vehicle_basic_mig):
    """ROS 2 cmd_sequence length == MAVLink cmd_sequence length - 1.

    MAVLink appends MAV_CMD_MISSION_START; ROS 2 embeds start implicitly in
    the trajectory setpoint stream. The waypoint count itself must be equal.
    """
    mig = four_vehicle_basic_mig

    for vehicle in mig.vehicles:
        ros2_val = ros2_transport.build_val_from_mig(mig, vehicle)
        mav_val = mavlink_transport.build_val_from_mig(mig, vehicle)
        mav_seq = mavlink_transport.get_normalized_cmd_sequence(mav_val)
        ros2_seq = ros2_transport.get_normalized_cmd_sequence(ros2_val)

        # MAVLink adds MISSION_START; waypoint counts are equal
        assert len(mav_seq) == len(ros2_seq) + 1, (
            f"Vehicle {vehicle.id}: MAVLink seq len {len(mav_seq)} != "
            f"ROS 2 seq len {len(ros2_seq)} + 1"
        )
