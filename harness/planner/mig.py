"""
MIG builder utilities.

Provides factory functions for creating and serializing Mission Intent Graph objects.
No LLM calls — pure data construction.
"""

from datetime import datetime, timezone
from uuid import uuid4

from harness.api.models import Constraints, MIG, MissionStatus, Vehicle, Waypoint


def new_mission_id() -> str:
    """Generate a short, readable mission ID."""
    return f"MSN-{uuid4().hex[:8].upper()}"


def build_mig(
    intent: str,
    mission_id: str,
    vehicles: list[Vehicle],
    waypoints: list[Waypoint],
    constraints: Constraints,
) -> MIG:
    """Construct a MIG from its constituent parts."""
    return MIG(
        mission_id=mission_id,
        created_at=datetime.now(timezone.utc),
        intent=intent,
        vehicles=vehicles,
        waypoints=waypoints,
        constraints=constraints,
        status=MissionStatus.planning,
        validation_errors=[],
    )


def mig_to_dict(mig: MIG) -> dict:
    """Serialize MIG to a plain dict (JSON-safe)."""
    return mig.model_dump(mode="json")


def mig_from_dict(d: dict) -> MIG:
    """Deserialize MIG from a plain dict."""
    return MIG.model_validate(d)
