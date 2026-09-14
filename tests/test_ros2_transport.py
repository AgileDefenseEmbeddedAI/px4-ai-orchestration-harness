"""
Unit tests for harness/dispatch/ros2_transport.py.

Uses a mock rclpy publisher — no live SITL or ROS 2 installation required.
Tests verify:
  - dispatch_val is blocked without authorization (DispatchNotAuthorizedError)
  - correct VehicleCommand MAV_CMDs are published for each vehicle class
  - TrajectorySetpoint is published for multirotors but NOT for rovers
  - commands are published in waypoint order
  - contingency ladder JSON file is written to sitl_workdir after dispatch
  - four_vehicle_basic.yaml scenario fixture matches expected command sequence
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from harness.api.models import (
    Constraints,
    MIG,
    MissionStatus,
    VAL,
    Vehicle,
    VehicleAction,
    VehicleType,
    Waypoint,
)
from harness.dispatch.ros2_transport import (
    MAV_CMD_NAV_RETURN_TO_LAUNCH,
    MAV_CMD_NAV_WAYPOINT,
    DispatchNotAuthorizedError,
    _action_to_mav_cmd,
    build_val_from_mig,
    dispatch_val,
)

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

GEOFENCE = [
    [35.1200, -79.0500],
    [35.1200, -78.9700],
    [35.1700, -78.9700],
    [35.1700, -79.0500],
]


@pytest.fixture
def sample_val_uav() -> VAL:
    """A three-action VAL for a multirotor (survey → loiter → rtl)."""
    return VAL(
        mission_id="MSN-TESTROS2",
        vehicle_id="UAV-1",
        vehicle_type=VehicleType.multirotor,
        actions=[
            VehicleAction(
                action_type="goto_waypoint",
                waypoint={"lat": 35.149, "lon": -79.010, "alt_m": 60.0, "role": "survey"},
                parameters={"speed_mps": 5.0},
            ),
            VehicleAction(
                action_type="goto_waypoint",
                waypoint={"lat": 35.151, "lon": -79.008, "alt_m": 60.0, "role": "loiter"},
                parameters={"speed_mps": 5.0},
            ),
            VehicleAction(
                action_type="goto_waypoint",
                waypoint={"lat": 35.140, "lon": -79.011, "alt_m": 30.0, "role": "rtl"},
                parameters={"speed_mps": 5.0},
            ),
        ],
    )


@pytest.fixture
def sample_val_gnd() -> VAL:
    """A three-action VAL for a rover (perimeter → perimeter → rtl)."""
    return VAL(
        mission_id="MSN-TESTROS2",
        vehicle_id="GND-1",
        vehicle_type=VehicleType.rover,
        actions=[
            VehicleAction(
                action_type="goto_waypoint",
                waypoint={"lat": 35.128, "lon": -79.040, "alt_m": 0.0, "role": "perimeter"},
                parameters={"speed_mps": 2.0},
            ),
            VehicleAction(
                action_type="goto_waypoint",
                waypoint={"lat": 35.130, "lon": -79.035, "alt_m": 0.0, "role": "perimeter"},
                parameters={"speed_mps": 2.0},
            ),
            VehicleAction(
                action_type="goto_waypoint",
                waypoint={"lat": 35.140, "lon": -79.011, "alt_m": 0.0, "role": "rtl"},
                parameters={"speed_mps": 2.0},
            ),
        ],
    )


@pytest.fixture
def mock_rclpy_env(monkeypatch):
    """
    Inject mock rclpy and px4_msgs into sys.modules so lazy imports in
    ros2_transport._ros2_publish resolve to mocks rather than raising ImportError.

    Returns a dict with handles for the mock node and publishers so tests can
    inspect publish() call counts and arguments.
    """
    mock_rclpy      = MagicMock()
    mock_msgs       = MagicMock()
    mock_node       = MagicMock()
    mock_cmd_pub    = MagicMock()
    mock_traj_pub   = MagicMock()

    mock_rclpy.ok.return_value = True
    mock_rclpy.create_node.return_value = mock_node

    def _create_publisher(msg_type, topic, qos):
        if "vehicle_command" in topic:
            return mock_cmd_pub
        return mock_traj_pub

    mock_node.create_publisher.side_effect = _create_publisher

    monkeypatch.setitem(sys.modules, "rclpy",          mock_rclpy)
    monkeypatch.setitem(sys.modules, "px4_msgs",       MagicMock())
    monkeypatch.setitem(sys.modules, "px4_msgs.msg",   mock_msgs)

    return {
        "rclpy":    mock_rclpy,
        "node":     mock_node,
        "cmd_pub":  mock_cmd_pub,
        "traj_pub": mock_traj_pub,
        "msgs":     mock_msgs,
    }


# ---------------------------------------------------------------------------
# Authorization gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_blocked_without_authorization(sample_val_uav: VAL) -> None:
    """dispatch_val must raise DispatchNotAuthorizedError when authorized=False."""
    with pytest.raises(DispatchNotAuthorizedError, match="dispatch blocked"):
        await dispatch_val(sample_val_uav, mission_id="MSN-TESTROS2", authorized=False)


@pytest.mark.asyncio
async def test_dispatch_blocked_by_default(sample_val_uav: VAL) -> None:
    """authorized defaults to False — dispatching without the flag raises."""
    with pytest.raises(DispatchNotAuthorizedError):
        await dispatch_val(sample_val_uav, mission_id="MSN-TESTROS2")


# ---------------------------------------------------------------------------
# Multirotor dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multirotor_publishes_vehicle_command_per_action(
    mock_rclpy_env, sample_val_uav: VAL, tmp_path: Path
) -> None:
    """One VehicleCommand is published for every action in the multirotor VAL."""
    result = await dispatch_val(
        sample_val_uav,
        mission_id="MSN-TESTROS2",
        namespace="/px4_1",
        authorized=True,
        sitl_workdir=str(tmp_path),
    )

    cmd_pub = mock_rclpy_env["cmd_pub"]
    assert cmd_pub.publish.call_count == len(sample_val_uav.actions)
    assert result["action_count"] == len(sample_val_uav.actions)
    assert result["transport"] == "ros2"


@pytest.mark.asyncio
async def test_multirotor_publishes_trajectory_setpoint_per_action(
    mock_rclpy_env, sample_val_uav: VAL, tmp_path: Path
) -> None:
    """TrajectorySetpoint is published alongside every VehicleCommand for multirotors."""
    await dispatch_val(
        sample_val_uav,
        mission_id="MSN-TESTROS2",
        namespace="/px4_1",
        authorized=True,
        sitl_workdir=str(tmp_path),
    )

    traj_pub = mock_rclpy_env["traj_pub"]
    assert traj_pub.publish.call_count == len(sample_val_uav.actions)


# ---------------------------------------------------------------------------
# Rover dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rover_publishes_only_vehicle_command(
    mock_rclpy_env, sample_val_gnd: VAL, tmp_path: Path
) -> None:
    """Rovers must NOT publish TrajectorySetpoint — only VehicleCommand."""
    await dispatch_val(
        sample_val_gnd,
        mission_id="MSN-TESTROS2",
        namespace="/px4_2",
        authorized=True,
        sitl_workdir=str(tmp_path),
    )

    assert mock_rclpy_env["cmd_pub"].publish.call_count == len(sample_val_gnd.actions)
    mock_rclpy_env["traj_pub"].publish.assert_not_called()


# ---------------------------------------------------------------------------
# Waypoint order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commands_published_in_waypoint_order(
    mock_rclpy_env, sample_val_uav: VAL, tmp_path: Path
) -> None:
    """VehicleCommand messages appear in the same order as val.actions."""
    result = await dispatch_val(
        sample_val_uav,
        mission_id="MSN-TESTROS2",
        namespace="/px4_1",
        authorized=True,
        sitl_workdir=str(tmp_path),
    )

    published = result["ros2"]["published"]
    assert len(published) == len(sample_val_uav.actions)

    for i, (action, pub) in enumerate(zip(sample_val_uav.actions, published)):
        expected_cmd = _action_to_mav_cmd(action, VehicleType.multirotor)
        assert pub["command"] == expected_cmd, (
            f"Action {i}: expected MAV_CMD {expected_cmd}, got {pub['command']}"
        )


@pytest.mark.asyncio
async def test_rtl_waypoint_maps_to_mav_cmd_rtl(
    mock_rclpy_env, sample_val_uav: VAL, tmp_path: Path
) -> None:
    """The last action (role=rtl) must emit MAV_CMD_NAV_RETURN_TO_LAUNCH (20)."""
    result = await dispatch_val(
        sample_val_uav,
        mission_id="MSN-TESTROS2",
        namespace="/px4_1",
        authorized=True,
        sitl_workdir=str(tmp_path),
    )

    published = result["ros2"]["published"]
    assert published[-1]["command"] == MAV_CMD_NAV_RETURN_TO_LAUNCH


@pytest.mark.asyncio
async def test_survey_waypoint_maps_to_mav_cmd_waypoint(
    mock_rclpy_env, sample_val_uav: VAL, tmp_path: Path
) -> None:
    """Non-rtl actions must emit MAV_CMD_NAV_WAYPOINT (16)."""
    result = await dispatch_val(
        sample_val_uav,
        mission_id="MSN-TESTROS2",
        namespace="/px4_1",
        authorized=True,
        sitl_workdir=str(tmp_path),
    )

    published = result["ros2"]["published"]
    assert published[0]["command"] == MAV_CMD_NAV_WAYPOINT


# ---------------------------------------------------------------------------
# Contingency ladder
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_contingency_ladder_file_written_for_uav(
    sample_val_uav: VAL, tmp_path: Path
) -> None:
    """Contingency ladder JSON must be present in sitl_workdir after dispatch."""
    await dispatch_val(
        sample_val_uav,
        mission_id="MSN-TESTROS2",
        authorized=True,
        sitl_workdir=str(tmp_path),
    )

    ladder_file = tmp_path / f"{sample_val_uav.vehicle_id}_contingency_ladder.json"
    assert ladder_file.exists(), "Contingency ladder file not found"

    data = json.loads(ladder_file.read_text())
    assert data["vehicle_id"]  == sample_val_uav.vehicle_id
    assert data["mission_id"]  == sample_val_uav.mission_id
    assert len(data["ladder"]) > 0


@pytest.mark.asyncio
async def test_contingency_ladder_file_written_for_rover(
    sample_val_gnd: VAL, tmp_path: Path
) -> None:
    """Rover dispatch also writes a contingency ladder file."""
    await dispatch_val(
        sample_val_gnd,
        mission_id="MSN-TESTROS2",
        authorized=True,
        sitl_workdir=str(tmp_path),
    )

    ladder_file = tmp_path / f"{sample_val_gnd.vehicle_id}_contingency_ladder.json"
    assert ladder_file.exists()

    data = json.loads(ladder_file.read_text())
    assert data["vehicle_type"] == "rover"


@pytest.mark.asyncio
async def test_contingency_ladder_written_before_any_publish(
    mock_rclpy_env, sample_val_uav: VAL, tmp_path: Path
) -> None:
    """Ladder file must exist even if rclpy publishing fails partway through."""
    # Make publish raise after first call to simulate mid-dispatch failure
    call_count = {"n": 0}

    def _failing_publish(msg):
        call_count["n"] += 1
        if call_count["n"] > 1:
            raise RuntimeError("simulated ROS 2 failure")

    mock_rclpy_env["cmd_pub"].publish.side_effect = _failing_publish

    with pytest.raises(RuntimeError, match="simulated ROS 2 failure"):
        await dispatch_val(
            sample_val_uav,
            mission_id="MSN-TESTROS2",
            namespace="/px4_1",
            authorized=True,
            sitl_workdir=str(tmp_path),
        )

    ladder_file = tmp_path / f"{sample_val_uav.vehicle_id}_contingency_ladder.json"
    assert ladder_file.exists(), "Ladder file must be written before publish calls start"


# ---------------------------------------------------------------------------
# Four-vehicle scenario fixture
# ---------------------------------------------------------------------------


SCENARIO_PATH = (
    Path(__file__).parent / "scenarios" / "four_vehicle_basic.yaml"
)


def _load_scenario() -> dict:
    with SCENARIO_PATH.open() as fh:
        return yaml.safe_load(fh)


def _mig_from_scenario(scenario: dict) -> MIG:
    plan = scenario["expected_plan"]
    return MIG(
        mission_id="MSN-4VEH-BASIC",
        intent=scenario["intent"],
        vehicles=[
            Vehicle(
                id=v["id"],
                vehicle_type=VehicleType(v["vehicle_type"]),
                sitl_target=v["sitl_target"],
                mavlink_sysid=v["mavlink_sysid"],
                waypoints=v["waypoints"],
            )
            for v in plan["vehicles"]
        ],
        waypoints=[
            Waypoint(
                id=w["id"],
                lat=w["lat"],
                lon=w["lon"],
                alt_m=w["alt_m"],
                role=w["role"],
            )
            for w in plan["waypoints"]
        ],
        constraints=Constraints(
            geofence_polygon=GEOFENCE,
            max_alt_m=120.0,
            min_alt_m=5.0,
            require_rtl=True,
        ),
        status=MissionStatus.pending_authorization,
    )


def test_four_vehicle_scenario_loads() -> None:
    """Scenario fixture must parse without errors and declare 4 vehicles."""
    scenario = _load_scenario()
    assert scenario["expected_plan"]["vehicle_count"] == 4
    assert len(scenario["expected_plan"]["vehicles"]) == 4
    assert len(scenario["expected_plan"]["waypoints"]) == 12


def test_four_vehicle_build_val_from_mig() -> None:
    """build_val_from_mig must produce one VAL per vehicle with correct action count."""
    scenario = _load_scenario()
    mig = _mig_from_scenario(scenario)

    assert len(mig.vehicles) == 4
    for vehicle in mig.vehicles:
        val = build_val_from_mig(mig, vehicle)
        assert val.vehicle_id   == vehicle.id
        assert val.vehicle_type == vehicle.vehicle_type
        assert len(val.actions) == len(vehicle.waypoints)


@pytest.mark.asyncio
async def test_four_vehicle_dispatch_command_sequence(
    mock_rclpy_env, tmp_path: Path
) -> None:
    """
    For each vehicle in the four_vehicle_basic scenario, dispatch_val must publish
    VehicleCommand messages whose MAV_CMD values match expected_dispatch in the YAML.
    """
    scenario = _load_scenario()
    mig      = _mig_from_scenario(scenario)
    expected = scenario["expected_dispatch"]  # dict[vehicle_id → list[{command, role}]]

    vehicle_map = {v.id: v for v in mig.vehicles}

    for vehicle_id, expected_cmds in expected.items():
        # Reset publish call counts between vehicles
        mock_rclpy_env["cmd_pub"].reset_mock()
        mock_rclpy_env["traj_pub"].reset_mock()

        vehicle = vehicle_map[vehicle_id]
        val     = build_val_from_mig(mig, vehicle)

        result = await dispatch_val(
            val,
            mission_id=mig.mission_id,
            namespace=f"/{vehicle_id.lower().replace('-', '_')}",
            authorized=True,
            sitl_workdir=str(tmp_path / vehicle_id),
        )

        published = result["ros2"]["published"]
        assert len(published) == len(expected_cmds), (
            f"{vehicle_id}: expected {len(expected_cmds)} commands, got {len(published)}"
        )
        for i, (pub, exp) in enumerate(zip(published, expected_cmds)):
            assert pub["command"] == exp["command"], (
                f"{vehicle_id} action {i}: expected MAV_CMD {exp['command']}, "
                f"got {pub['command']}"
            )
