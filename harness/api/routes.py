"""
FastAPI API router.

Endpoints:
  POST /intent              — submit natural-language mission intent
  GET  /plan/{mission_id}   — retrieve current plan/status
  POST /authorize/{mission_id} — human authorization gate
  GET  /missions            — list all missions (summary)
  GET  /audit/{mission_id}  — retrieve audit log entries
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from harness.api.models import (
    AuthorizeRequest,
    IntentRequest,
    MissionResponse,
    MissionStatus,
)
from harness.audit import logger as audit_module
from harness.planner import mig_builder, plan_decomposer
from harness.planner.mig import new_mission_id
from harness.validator import constraint_checker

router = APIRouter()
logger = logging.getLogger(__name__)

_MISSIONS_DIR = Path(__file__).parents[2] / "missions"


def _store_mission_artifact(mission_id: str, mig_dict: dict, plans: list[dict]) -> None:
    """Write MIG + plans to missions/<mission_id>.json for audit/replay."""
    _MISSIONS_DIR.mkdir(exist_ok=True)
    artifact = {"mig": mig_dict, "plans": plans}
    path = _MISSIONS_DIR / f"{mission_id}.json"
    path.write_text(json.dumps(artifact, indent=2, default=str))


# ---------------------------------------------------------------------------
# Background task: dispatch
# ---------------------------------------------------------------------------


async def _dispatch_mission(
    mission_id: str,
    missions: dict,
    vehicles_config: dict,
) -> None:
    """Dispatch all vehicles in the MIG via both transports."""
    from harness.dispatch.mavlink_transport import dispatch_val as mavlink_dispatch
    from harness.dispatch.ros2_transport import build_val_from_mig
    from harness.dispatch.ros2_transport import dispatch_val as ros2_dispatch

    try:
        mission = missions[mission_id]
        mig = mission.mig
        if mig is None:
            raise RuntimeError("MIG is missing; cannot dispatch")

        missions[mission_id].status = MissionStatus.dispatching
        audit_module.log_event(
            mission_id, "dispatch_started", {"vehicle_count": len(mig.vehicles)}
        )

        # Build a fleet lookup for MAVLink connection strings
        fleet_by_id = {v["id"]: v for v in vehicles_config.get("fleet", [])}

        for vehicle in mig.vehicles:
            val = build_val_from_mig(mig, vehicle)

            # Primary: ROS 2 transport
            ros2_result = await ros2_dispatch(val)
            audit_module.log_event(
                mission_id,
                "ros2_dispatch",
                {"vehicle_id": vehicle.id, "result": ros2_result},
            )

            # Secondary: MAVLink 2 transport
            fleet_entry = fleet_by_id.get(vehicle.id, {})
            connection = fleet_entry.get("mavlink_connection", "udp:127.0.0.1:14540")
            mavlink_result = await mavlink_dispatch(val, connection)
            audit_module.log_event(
                mission_id,
                "mavlink_dispatch",
                {"vehicle_id": vehicle.id, "result": mavlink_result},
            )

        missions[mission_id].status = MissionStatus.dispatched
        audit_module.log_event(mission_id, "dispatch_complete", {"mission_id": mission_id})

    except Exception as exc:
        logger.exception(f"Dispatch failed for mission {mission_id}: {exc}")
        missions[mission_id].status = MissionStatus.failed
        audit_module.log_event(mission_id, "dispatch_error", {"error": str(exc)})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/intent", summary="Submit mission intent")
async def post_intent(
    body: IntentRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Accept a natural-language mission intent.

    Runs the LLM decomposer synchronously, validates the resulting MIG, and
    expands it into per-vehicle plans.  Returns the full MIG and plan list so
    the operator can review before authorizing.
    """
    mission_id = new_mission_id()
    missions: dict = request.app.state.missions
    config: dict = request.app.state.config
    constraints_config: dict = request.app.state.constraints_config

    missions[mission_id] = MissionResponse(
        mission_id=mission_id,
        status=MissionStatus.planning,
        validation_errors=[],
    )

    try:
        audit_module.log_event(mission_id, "planning_started", {"intent": body.text})

        mig = await mig_builder.build_mig_from_intent(body.text, config)
        mig.mission_id = mission_id

        audit_module.log_event(
            mission_id,
            "mig_generated",
            {"vehicle_count": len(mig.vehicles), "waypoint_count": len(mig.waypoints)},
        )

        is_valid, errors = constraint_checker.validate(mig, constraints_config)

        if is_valid:
            mig.status = MissionStatus.pending_authorization
            audit_module.log_event(mission_id, "validation_passed", {})
        else:
            mig.status = MissionStatus.validation_failed
            mig.validation_errors = errors
            audit_module.log_event(mission_id, "validation_failed", {"errors": errors})

        plans = plan_decomposer.decompose(mig)

        mig_dict = mig.model_dump(mode="json")
        plans_list = [p.model_dump(mode="json") for p in plans]
        _store_mission_artifact(mission_id, mig_dict, plans_list)

        missions[mission_id].mig = mig
        missions[mission_id].status = mig.status
        missions[mission_id].validation_errors = mig.validation_errors

        return {
            "mission_id": mission_id,
            "status": mig.status,
            "mig": mig_dict,
            "plan": plans_list,
        }

    except Exception as exc:
        logger.exception("Planning failed for mission %s: %s", mission_id, exc)
        missions[mission_id].status = MissionStatus.failed
        audit_module.log_event(mission_id, "planning_error", {"error": str(exc)})
        return {"mission_id": mission_id, "status": MissionStatus.failed}


@router.get("/plan/{mission_id}", response_model=MissionResponse, summary="Get plan/status")
async def get_plan(mission_id: str, request: Request):
    """Return the current state of a mission."""
    missions: dict = request.app.state.missions
    if mission_id not in missions:
        raise HTTPException(status_code=404, detail=f"Mission '{mission_id}' not found")
    return missions[mission_id]


@router.post("/authorize/{mission_id}", response_model=MissionResponse, summary="Authorize or reject mission")
async def authorize_mission(
    mission_id: str,
    body: AuthorizeRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Human authorization gate.

    The mission must be in pending_authorization state.
    If authorized=True, sets status to authorized and starts dispatch.
    If authorized=False, marks the mission as failed.
    """
    missions: dict = request.app.state.missions
    if mission_id not in missions:
        raise HTTPException(status_code=404, detail=f"Mission '{mission_id}' not found")

    mission = missions[mission_id]

    if mission.status == MissionStatus.planning:
        raise HTTPException(status_code=409, detail="Mission is still being planned; try again shortly")

    if mission.status == MissionStatus.validation_failed:
        raise HTTPException(
            status_code=409,
            detail="Mission failed validation and cannot be authorized",
        )

    if mission.status not in (MissionStatus.pending_authorization,):
        raise HTTPException(
            status_code=409,
            detail=f"Mission is not pending authorization (current status: {mission.status})",
        )

    if not body.authorized:
        mission.status = MissionStatus.failed
        audit_module.log_event(
            mission_id, "authorization_rejected", {"operator": body.operator}
        )
        return mission

    now = datetime.now(timezone.utc)
    mission.status = MissionStatus.authorized
    mission.authorized_at = now
    mission.authorized_by = body.operator

    audit_module.log_event(
        mission_id,
        "authorization_granted",
        {"operator": body.operator, "authorized_at": now.isoformat()},
    )

    background_tasks.add_task(
        _dispatch_mission,
        mission_id,
        missions,
        request.app.state.vehicles_config,
    )

    return mission


@router.get("/missions", summary="List all missions")
async def list_missions(request: Request):
    """Return a summary list of all missions."""
    missions: dict = request.app.state.missions
    return [
        {
            "mission_id": m.mission_id,
            "status": m.status,
            "intent": m.mig.intent if m.mig else None,
            "vehicle_count": len(m.mig.vehicles) if m.mig else 0,
        }
        for m in missions.values()
    ]


@router.get("/audit/{mission_id}", summary="Get mission audit log")
async def get_audit(mission_id: str):
    """Return all audit log entries for a mission."""
    from harness.audit.logger import read_log

    entries = read_log(mission_id)
    return entries
