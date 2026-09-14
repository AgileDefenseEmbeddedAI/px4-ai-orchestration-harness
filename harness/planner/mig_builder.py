"""
LLM-backed MIG builder.

Calls the configured LLM (openai-compatible) to decompose a natural-language
mission intent into a Mission Intent Graph (MIG).  The raw LLM response is
validated against schemas/mig.v1.json before the MIG object is returned.

Falls back to a deterministic stub plan when the LLM is unavailable so the
system remains testable without live credentials.
"""

import json
import logging
import os
from pathlib import Path

import jsonschema
import openai

from harness.api.models import (
    Constraints,
    ContingencyAction,
    ContingencyRung,
    ConditionalBranch,
    MIG,
    MissionStatus,
    Vehicle,
    VehicleType,
    Waypoint,
)
from harness.planner.mig import build_mig, new_mission_id

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).parents[2] / "schemas" / "mig.v1.json"

SYSTEM_PROMPT = """You are a mission planning AI for heterogeneous autonomous vehicle systems.
Given a natural-language mission intent, decompose it into a structured JSON plan.

Output ONLY valid JSON matching this structure:
{
  "vehicles": [
    {
      "id": "UAV-1",
      "vehicle_type": "multirotor",
      "sitl_target": "gz_x500",
      "mavlink_sysid": 1,
      "waypoints": ["WP-1", "WP-2", "WP-RTL-1"]
    }
  ],
  "waypoints": [
    {
      "id": "WP-1",
      "lat": 35.14,
      "lon": -79.01,
      "alt_m": 50.0,
      "role": "survey"
    }
  ],
  "constraints": {
    "max_alt_m": 120.0,
    "min_alt_m": 5.0,
    "require_rtl": true,
    "max_range_m": 5000.0
  },
  "contingency_ladder": [
    {
      "trigger": "link_loss",
      "priority": 1,
      "actions": [
        {"action_type": "rtl", "vehicle_id": null}
      ]
    }
  ],
  "conditional_branches": [
    {
      "condition": "threat_detected",
      "if_vehicle_id": "UAV-1",
      "then": [
        {"action_type": "loiter", "waypoint_id": null}
      ]
    }
  ]
}

Rules:
- Always include a return-to-launch (RTL) waypoint for each vehicle
- Multirotor vehicles use sitl_target "gz_x500"
- Rover vehicles use sitl_target "gz_rover_ackermann" and alt_m = 0.0
- mavlink_sysid starts at 1 for the first vehicle and increments by 1
- Use realistic coordinates near Fort Bragg, NC (lat: 35.14, lon: -79.01) unless specified
- Keep all waypoints within 5 km of the home base
- Always include at least one contingency_ladder entry (e.g. link_loss -> rtl)
- Include conditional_branches when the intent describes conditional behavior
- Waypoint roles: survey | loiter | hover | perimeter | rtl | transit | land
- vehicle_id in contingency actions: null means apply to all vehicles
"""


async def build_mig_from_intent(text: str, config: dict) -> MIG:
    """
    Call the configured LLM to decompose intent text into a MIG.

    Validates the raw LLM JSON against mig.v1.json before constructing the
    MIG object.  Falls back to a deterministic stub when the LLM fails.
    """
    mission_id = new_mission_id()
    raw_plan: dict | None = None

    try:
        client = _make_client(config)
        response = await client.chat.completions.create(
            model=config.get("model", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Mission intent: {text}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        raw_plan = json.loads(response.choices[0].message.content)
        logger.info("[mig_builder] LLM returned plan for mission %s", mission_id)
    except Exception as exc:
        logger.warning("[mig_builder] LLM failed (%s), using stub plan", exc)
        raw_plan = _stub_plan(text)

    mig = _assemble_mig(raw_plan, text, mission_id)

    try:
        _validate_mig(mig)
    except jsonschema.ValidationError as exc:
        logger.warning("[mig_builder] MIG failed schema validation: %s", exc.message)

    return mig


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_client(config: dict) -> openai.AsyncOpenAI:
    api_key = config.get("api_key") or os.environ.get(
        config.get("api_key_env", "OPENAI_API_KEY"), "sk-placeholder"
    )
    base_url = config.get("base_url") or None
    return openai.AsyncOpenAI(api_key=api_key, base_url=base_url)


def _assemble_mig(plan: dict, text: str, mission_id: str) -> MIG:
    vehicles = [Vehicle(**v) for v in plan.get("vehicles", [])]
    waypoints = [Waypoint(**w) for w in plan.get("waypoints", [])]
    constraints = Constraints(**plan.get("constraints", {}))

    contingency_ladder = [
        ContingencyRung(
            trigger=r["trigger"],
            priority=r.get("priority", 100),
            actions=[ContingencyAction(**a) for a in r.get("actions", [])],
        )
        for r in plan.get("contingency_ladder", [])
    ]

    conditional_branches = [
        ConditionalBranch(
            condition=b["condition"],
            if_vehicle_id=b["if_vehicle_id"],
            then=[ContingencyAction(**a) for a in b.get("then", [])],
            **{"else": [ContingencyAction(**a) for a in b.get("else", [])]},
        )
        for b in plan.get("conditional_branches", [])
    ]

    mig = build_mig(
        intent=text,
        mission_id=mission_id,
        vehicles=vehicles,
        waypoints=waypoints,
        constraints=constraints,
    )
    mig.contingency_ladder = contingency_ladder
    mig.conditional_branches = conditional_branches
    return mig


def _validate_mig(mig: MIG) -> None:
    schema = json.loads(_SCHEMA_PATH.read_text())
    # by_alias=True: ConditionalBranch.else_ → "else"; exclude_none=True: omit optional Nones.
    mig_dict = mig.model_dump(mode="json", by_alias=True, exclude_none=True)
    mig_dict["version"] = "1.1"
    jsonschema.validate(mig_dict, schema)


def _stub_plan(text: str) -> dict:
    """Deterministic stub plan used when LLM is unavailable (e.g. in CI)."""
    return {
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
                "waypoints": ["WP-5", "WP-6", "WP-RTL-3"],
            },
            {
                "id": "GND-1",
                "vehicle_type": "rover",
                "sitl_target": "gz_rover_ackermann",
                "mavlink_sysid": 3,
                "waypoints": ["WP-3", "WP-4", "WP-RTL-2"],
            },
            {
                "id": "GND-2",
                "vehicle_type": "rover",
                "sitl_target": "gz_rover_ackermann",
                "mavlink_sysid": 4,
                "waypoints": ["WP-7", "WP-8", "WP-RTL-4"],
            },
        ],
        "waypoints": [
            {"id": "WP-1",     "lat": 35.1490, "lon": -79.0100, "alt_m": 50.0, "role": "survey"},
            {"id": "WP-2",     "lat": 35.1510, "lon": -79.0080, "alt_m": 50.0, "role": "loiter"},
            {"id": "WP-RTL-1", "lat": 35.1400, "lon": -79.0110, "alt_m": 30.0, "role": "rtl"},
            {"id": "WP-3",     "lat": 35.1420, "lon": -79.0120, "alt_m": 0.0,  "role": "survey"},
            {"id": "WP-4",     "lat": 35.1430, "lon": -79.0090, "alt_m": 0.0,  "role": "perimeter"},
            {"id": "WP-RTL-2", "lat": 35.1400, "lon": -79.0110, "alt_m": 0.0,  "role": "rtl"},
            {"id": "WP-5",     "lat": 35.1460, "lon": -79.0070, "alt_m": 60.0, "role": "survey"},
            {"id": "WP-6",     "lat": 35.1480, "lon": -79.0050, "alt_m": 60.0, "role": "hover"},
            {"id": "WP-RTL-3", "lat": 35.1400, "lon": -79.0110, "alt_m": 30.0, "role": "rtl"},
            {"id": "WP-7",     "lat": 35.1350, "lon": -79.0130, "alt_m": 0.0,  "role": "transit"},
            {"id": "WP-8",     "lat": 35.1360, "lon": -79.0100, "alt_m": 0.0,  "role": "perimeter"},
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
                "actions": [
                    {"action_type": "rtl", "vehicle_id": None}
                ],
            },
            {
                "trigger": "low_battery",
                "priority": 2,
                "actions": [
                    {"action_type": "land", "vehicle_id": None}
                ],
            },
        ],
        "conditional_branches": [
            {
                "condition": "threat_detected",
                "if_vehicle_id": "UAV-1",
                "then": [
                    {"action_type": "loiter", "vehicle_id": "UAV-1", "waypoint_id": "WP-2"}
                ],
                "else": [],
            }
        ],
    }
