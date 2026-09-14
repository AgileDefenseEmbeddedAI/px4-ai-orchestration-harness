"""
Tests for the MIG builder and plan decomposer.

Uses a recorded LLM-response fixture (no live network required in CI).
The LLM call is monkeypatched to return a pre-canned JSON payload so tests
are fully deterministic.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import jsonschema
import pytest
from pathlib import Path

from harness.api.models import (
    Constraints,
    MIG,
    MissionStatus,
    Vehicle,
    VehicleType,
    Waypoint,
    Plan,
)
from harness.planner import mig_builder, plan_decomposer
from harness.planner.mig import build_mig, new_mission_id

# ---------------------------------------------------------------------------
# Paths to versioned schemas
# ---------------------------------------------------------------------------

_SCHEMA_DIR = Path(__file__).parents[1] / "schemas"
_MIG_SCHEMA = json.loads((_SCHEMA_DIR / "mig.v1.json").read_text())
_PLAN_SCHEMA = json.loads((_SCHEMA_DIR / "plan.v1.json").read_text())

# ---------------------------------------------------------------------------
# Recorded LLM fixture response (four vehicles, contingency + conditional)
# ---------------------------------------------------------------------------

RECORDED_LLM_RESPONSE = {
    "vehicles": [
        {
            "id": "UAV-1",
            "vehicle_type": "multirotor",
            "sitl_target": "gz_x500",
            "mavlink_sysid": 1,
            "waypoints": ["WP-1", "WP-2", "WP-RTL-1"],
        },
        {
            "id": "UAV-2",
            "vehicle_type": "multirotor",
            "sitl_target": "gz_x500",
            "mavlink_sysid": 2,
            "waypoints": ["WP-3", "WP-RTL-2"],
        },
        {
            "id": "GND-1",
            "vehicle_type": "rover",
            "sitl_target": "gz_rover_ackermann",
            "mavlink_sysid": 3,
            "waypoints": ["WP-4", "WP-5", "WP-RTL-3"],
        },
        {
            "id": "GND-2",
            "vehicle_type": "rover",
            "sitl_target": "gz_rover_ackermann",
            "mavlink_sysid": 4,
            "waypoints": ["WP-6", "WP-RTL-4"],
        },
    ],
    "waypoints": [
        {"id": "WP-1",     "lat": 35.1490, "lon": -79.0100, "alt_m": 50.0, "role": "survey"},
        {"id": "WP-2",     "lat": 35.1510, "lon": -79.0080, "alt_m": 50.0, "role": "loiter"},
        {"id": "WP-RTL-1", "lat": 35.1400, "lon": -79.0110, "alt_m": 30.0, "role": "rtl"},
        {"id": "WP-3",     "lat": 35.1460, "lon": -79.0070, "alt_m": 60.0, "role": "hover"},
        {"id": "WP-RTL-2", "lat": 35.1400, "lon": -79.0110, "alt_m": 30.0, "role": "rtl"},
        {"id": "WP-4",     "lat": 35.1420, "lon": -79.0120, "alt_m": 0.0,  "role": "survey"},
        {"id": "WP-5",     "lat": 35.1430, "lon": -79.0090, "alt_m": 0.0,  "role": "perimeter"},
        {"id": "WP-RTL-3", "lat": 35.1400, "lon": -79.0110, "alt_m": 0.0,  "role": "rtl"},
        {"id": "WP-6",     "lat": 35.1350, "lon": -79.0130, "alt_m": 0.0,  "role": "transit"},
        {"id": "WP-RTL-4", "lat": 35.1400, "lon": -79.0110, "alt_m": 0.0,  "role": "rtl"},
    ],
    "constraints": {
        "max_alt_m": 120.0,
        "min_alt_m": 5.0,
        "require_rtl": True,
        "max_range_m": 5000.0,
    },
    "contingency_ladder": [
        {
            "trigger": "link_loss",
            "priority": 1,
            "actions": [{"action_type": "rtl", "vehicle_id": None}],
        },
        {
            "trigger": "low_battery",
            "priority": 2,
            "actions": [{"action_type": "land", "vehicle_id": None}],
        },
    ],
    "conditional_branches": [
        {
            "condition": "threat_detected",
            "if_vehicle_id": "UAV-1",
            "then": [{"action_type": "loiter", "vehicle_id": "UAV-1", "waypoint_id": "WP-2"}],
            "else": [],
        }
    ],
}

FOUR_VEHICLE_INTENT = (
    "Scout grid Alpha-7 with two UAVs and have two rovers secure the perimeter; "
    "if threat detected, loiter UAV-1; all vehicles RTL on link loss"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_llm_response(payload: dict):
    """Build a minimal mock that looks like an openai ChatCompletion response."""
    msg = MagicMock()
    msg.content = json.dumps(payload)
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# mig_builder tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_mig_from_intent_returns_mig_with_llm_fixture():
    """MIG builder returns a valid MIG when the LLM responds with the fixture."""
    fake_response = _make_fake_llm_response(RECORDED_LLM_RESPONSE)

    with patch("harness.planner.mig_builder._make_client") as mock_make_client:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_response)
        mock_make_client.return_value = mock_client

        mig = await mig_builder.build_mig_from_intent(
            FOUR_VEHICLE_INTENT,
            {"model": "gpt-4o-mini", "api_key": "sk-test"},
        )

    assert isinstance(mig, MIG)
    assert len(mig.vehicles) == 4
    assert len(mig.waypoints) == 10


def test_mig_has_contingency_ladder_with_llm_fixture():
    """MIG assembled from fixture has at least one contingency_ladder entry."""
    mig = mig_builder._assemble_mig(
        RECORDED_LLM_RESPONSE, FOUR_VEHICLE_INTENT, "MSN-TESTTEST"
    )
    assert len(mig.contingency_ladder) >= 1
    assert any(r.trigger == "link_loss" for r in mig.contingency_ladder)


def test_mig_has_conditional_branches_with_llm_fixture():
    """MIG assembled from fixture has at least one conditional_branch."""
    mig = mig_builder._assemble_mig(
        RECORDED_LLM_RESPONSE, FOUR_VEHICLE_INTENT, "MSN-TESTTEST"
    )
    assert len(mig.conditional_branches) >= 1
    assert mig.conditional_branches[0].condition == "threat_detected"
    assert mig.conditional_branches[0].if_vehicle_id == "UAV-1"


@pytest.mark.asyncio
async def test_build_mig_falls_back_to_stub_on_llm_failure():
    """When the LLM raises, mig_builder returns a stub plan (not None)."""
    with patch("harness.planner.mig_builder._make_client") as mock_make_client:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("no LLM"))
        mock_make_client.return_value = mock_client

        mig = await mig_builder.build_mig_from_intent(
            "Scout the area with four vehicles and RTL on link loss",
            {"model": "gpt-4o-mini", "api_key": "sk-test"},
        )

    assert isinstance(mig, MIG)
    assert len(mig.vehicles) >= 2
    assert len(mig.contingency_ladder) >= 1


def test_stub_plan_has_contingency_and_conditional():
    """The built-in stub plan always includes contingency and conditional fields."""
    plan = mig_builder._stub_plan("test intent")
    assert "contingency_ladder" in plan
    assert len(plan["contingency_ladder"]) >= 1
    assert "conditional_branches" in plan
    assert len(plan["conditional_branches"]) >= 1


# ---------------------------------------------------------------------------
# MIG schema validation tests
# ---------------------------------------------------------------------------


def test_assembled_mig_validates_against_mig_v1_schema():
    """MIG assembled from the fixture validates against schemas/mig.v1.json."""
    mig = mig_builder._assemble_mig(
        RECORDED_LLM_RESPONSE, FOUR_VEHICLE_INTENT, "MSN-A1B2C3D4"
    )
    # by_alias=True so ConditionalBranch.else_ serializes as "else" (schema key)
    # exclude_none=True omits optional None fields like Waypoint.timing
    mig_dict = mig.model_dump(mode="json", by_alias=True, exclude_none=True)
    mig_dict["version"] = "1.1"  # schema requires "1.1"
    jsonschema.validate(mig_dict, _MIG_SCHEMA)  # raises if invalid


# ---------------------------------------------------------------------------
# plan_decomposer tests
# ---------------------------------------------------------------------------


def test_decompose_produces_one_plan_per_vehicle():
    """decompose() returns exactly one Plan per MIG vehicle."""
    mig = mig_builder._assemble_mig(
        RECORDED_LLM_RESPONSE, FOUR_VEHICLE_INTENT, "MSN-TESTTEST"
    )
    plans = plan_decomposer.decompose(mig)
    assert len(plans) == len(mig.vehicles)


def test_multirotor_plan_uses_only_multirotor_legal_commands():
    """Multirotor plan must not contain rover-only or illegal commands."""
    mig = mig_builder._assemble_mig(
        RECORDED_LLM_RESPONSE, FOUR_VEHICLE_INTENT, "MSN-TESTTEST"
    )
    plans = plan_decomposer.decompose(mig)

    multirotor_plans = [p for p in plans if p.vehicle_type == VehicleType.multirotor]
    assert multirotor_plans, "expected at least one multirotor plan"

    legal_cmds = {
        "MAV_CMD_NAV_WAYPOINT",
        "MAV_CMD_NAV_LOITER_UNLIM",
        "MAV_CMD_NAV_RETURN_TO_LAUNCH",
        "MAV_CMD_NAV_LAND",
        "MAV_CMD_NAV_TAKEOFF",
    }
    for plan in multirotor_plans:
        for cmd in plan.commands:
            assert cmd.mav_cmd in legal_cmds, f"illegal command {cmd.mav_cmd} in multirotor plan"


def test_rover_plan_uses_only_rover_legal_commands():
    """Rover plan must only use ground-vehicle-legal commands (no loiter/hover)."""
    mig = mig_builder._assemble_mig(
        RECORDED_LLM_RESPONSE, FOUR_VEHICLE_INTENT, "MSN-TESTTEST"
    )
    plans = plan_decomposer.decompose(mig)

    rover_plans = [p for p in plans if p.vehicle_type == VehicleType.rover]
    assert rover_plans, "expected at least one rover plan"

    illegal_cmds = {"MAV_CMD_NAV_LOITER_UNLIM", "MAV_CMD_NAV_LAND", "MAV_CMD_NAV_TAKEOFF"}
    for plan in rover_plans:
        for cmd in plan.commands:
            assert cmd.mav_cmd not in illegal_cmds, (
                f"rover plan contains illegal command {cmd.mav_cmd}"
            )


def test_rover_plan_alt_is_zero():
    """All rover commands must have alt_m = 0.0."""
    mig = mig_builder._assemble_mig(
        RECORDED_LLM_RESPONSE, FOUR_VEHICLE_INTENT, "MSN-TESTTEST"
    )
    plans = plan_decomposer.decompose(mig)

    for plan in plans:
        if plan.vehicle_type != VehicleType.rover:
            continue
        for cmd in plan.commands:
            assert cmd.alt_m == 0.0, (
                f"rover command has non-zero alt_m={cmd.alt_m} for {cmd.mav_cmd}"
            )


def test_loiter_role_maps_to_loiter_command_for_multirotor():
    """Waypoints with role='loiter' or 'hover' produce MAV_CMD_NAV_LOITER_UNLIM for multirotors."""
    mig = mig_builder._assemble_mig(
        RECORDED_LLM_RESPONSE, FOUR_VEHICLE_INTENT, "MSN-TESTTEST"
    )
    plans = plan_decomposer.decompose(mig)

    for plan in plans:
        if plan.vehicle_type != VehicleType.multirotor:
            continue
        for cmd in plan.commands:
            if cmd.role in ("loiter", "hover"):
                assert cmd.mav_cmd == "MAV_CMD_NAV_LOITER_UNLIM", (
                    f"role={cmd.role} should map to LOITER_UNLIM, got {cmd.mav_cmd}"
                )


def test_rtl_role_maps_to_rtl_command():
    """Waypoints with role='rtl' must produce MAV_CMD_NAV_RETURN_TO_LAUNCH for all vehicle types."""
    mig = mig_builder._assemble_mig(
        RECORDED_LLM_RESPONSE, FOUR_VEHICLE_INTENT, "MSN-TESTTEST"
    )
    plans = plan_decomposer.decompose(mig)

    for plan in plans:
        for cmd in plan.commands:
            if cmd.role == "rtl":
                assert cmd.mav_cmd == "MAV_CMD_NAV_RETURN_TO_LAUNCH", (
                    f"rtl role produced {cmd.mav_cmd} instead of RTL"
                )


def test_plan_validates_against_plan_v1_schema():
    """Every plan produced from the fixture validates against schemas/plan.v1.json."""
    mig = mig_builder._assemble_mig(
        RECORDED_LLM_RESPONSE, FOUR_VEHICLE_INTENT, "MSN-TESTTEST"
    )
    plans = plan_decomposer.decompose(mig)

    for plan in plans:
        plan_dict = plan.model_dump(mode="json")
        jsonschema.validate(plan_dict, _PLAN_SCHEMA)


def test_plan_commands_are_sequenced():
    """Commands in each plan must be numbered 0, 1, 2, ... without gaps."""
    mig = mig_builder._assemble_mig(
        RECORDED_LLM_RESPONSE, FOUR_VEHICLE_INTENT, "MSN-TESTTEST"
    )
    plans = plan_decomposer.decompose(mig)

    for plan in plans:
        seqs = [cmd.seq for cmd in plan.commands]
        assert seqs == list(range(len(seqs))), (
            f"plan for {plan.vehicle_id} has non-sequential command seqs: {seqs}"
        )


# ---------------------------------------------------------------------------
# POST /intent integration test (checks new response shape)
# ---------------------------------------------------------------------------


def test_post_intent_returns_mig_and_plan(app_client):
    """POST /intent should return mission_id, status, mig, and plan in the response."""
    response = app_client.post("/intent", json={"text": FOUR_VEHICLE_INTENT})
    assert response.status_code == 200
    data = response.json()
    assert "mission_id" in data
    assert "status" in data
    assert "mig" in data
    assert "plan" in data
    assert isinstance(data["plan"], list)
    assert len(data["plan"]) >= 1


def test_post_intent_plan_vehicle_types_match_mig(app_client):
    """Each plan in the response has a vehicle_type that matches the MIG vehicles."""
    response = app_client.post("/intent", json={"text": FOUR_VEHICLE_INTENT})
    assert response.status_code == 200
    data = response.json()

    mig_vehicle_ids = {v["id"] for v in data["mig"]["vehicles"]}
    plan_vehicle_ids = {p["vehicle_id"] for p in data["plan"]}
    assert mig_vehicle_ids == plan_vehicle_ids
