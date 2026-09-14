"""
LLM-backed intent decomposer.

Calls the configured LLM to convert a natural-language mission intent into a
structured MIG. Falls back to a deterministic stub plan when the LLM is
unavailable, unreachable, or returns invalid JSON — so the system remains
testable without live credentials.

The LLM NEVER writes directly to a vehicle; it only produces JSON that the
validator checks before any dispatch.
"""

import json
import logging
import os

import openai

from harness.api.models import Constraints, MIG, Vehicle, VehicleType, Waypoint
from harness.planner.mig import build_mig, new_mission_id

logger = logging.getLogger(__name__)

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
      "waypoints": ["WP-1", "WP-2"]
    }
  ],
  "waypoints": [
    {
      "id": "WP-1",
      "lat": 47.3977,
      "lon": 8.5456,
      "alt_m": 50.0,
      "role": "survey"
    }
  ],
  "constraints": {
    "max_alt_m": 120.0,
    "min_alt_m": 5.0,
    "require_rtl": true,
    "max_range_m": 5000.0
  }
}

Rules:
- Always include a return-to-launch (RTL) waypoint for each vehicle
- Multirotor vehicles use sitl_target "gz_x500"
- Rover vehicles use sitl_target "gz_rover_ackermann" and alt_m = 0.0
- mavlink_sysid starts at 1 for first vehicle, increments by 1
- Use realistic coordinates near Fort Bragg, NC (lat: 35.14, lon: -79.01) unless specified otherwise
- Keep missions within 5km of the home base
"""


async def decompose_intent(text: str, config: dict) -> MIG:
    """
    Call the configured LLM to decompose intent text into a MIG.

    Falls back to a deterministic stub plan if the LLM is unavailable.
    """
    mission_id = new_mission_id()
    plan: dict | None = None

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
        raw = response.choices[0].message.content
        plan = json.loads(raw)
        logger.info(f"[decomposer] LLM returned plan for mission {mission_id}")
    except Exception as exc:
        logger.warning(f"[decomposer] LLM decomposition failed ({exc}), using stub plan")
        plan = _stub_plan(text)

    vehicles = [Vehicle(**v) for v in plan.get("vehicles", [])]
    waypoints = [Waypoint(**w) for w in plan.get("waypoints", [])]
    raw_constraints = plan.get("constraints", {})
    constraints = Constraints(**raw_constraints)

    return build_mig(
        intent=text,
        mission_id=mission_id,
        vehicles=vehicles,
        waypoints=waypoints,
        constraints=constraints,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_client(config: dict) -> openai.AsyncOpenAI:
    api_key = config.get("api_key") or os.environ.get(
        config.get("api_key_env", "OPENAI_API_KEY"), "sk-placeholder"
    )
    base_url = config.get("base_url") or None
    return openai.AsyncOpenAI(api_key=api_key, base_url=base_url)


def _stub_plan(text: str) -> dict:
    """Return a deterministic stub plan for testing without an LLM."""
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
                "id": "GND-1",
                "vehicle_type": "rover",
                "sitl_target": "gz_rover_ackermann",
                "mavlink_sysid": 2,
                "waypoints": ["WP-3", "WP-4", "WP-RTL-2"],
            },
        ],
        "waypoints": [
            {"id": "WP-1", "lat": 35.1490, "lon": -79.0100, "alt_m": 50.0, "role": "survey"},
            {"id": "WP-2", "lat": 35.1510, "lon": -79.0080, "alt_m": 50.0, "role": "loiter"},
            {"id": "WP-RTL-1", "lat": 35.1400, "lon": -79.0110, "alt_m": 30.0, "role": "rtl"},
            {"id": "WP-3", "lat": 35.1420, "lon": -79.0120, "alt_m": 0.0, "role": "survey"},
            {"id": "WP-4", "lat": 35.1430, "lon": -79.0090, "alt_m": 0.0, "role": "perimeter"},
            {"id": "WP-RTL-2", "lat": 35.1400, "lon": -79.0110, "alt_m": 0.0, "role": "rtl"},
        ],
        "constraints": {
            "max_alt_m": 120.0,
            "min_alt_m": 5.0,
            "require_rtl": True,
            "max_range_m": 5000.0,
        },
    }
