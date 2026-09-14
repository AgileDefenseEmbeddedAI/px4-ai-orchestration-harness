"""
Authorization router.

Endpoints:
  POST /authorize/{mission_id} — human authorization gate, audit logging, dispatch trigger

REQ-AUTH-01: No validated plan reaches a vehicle without explicit operator confirmation.
REQ-AUTH-02: The operator sees the full plan including all contingency branches.

The authorization event is written to the audit log BEFORE dispatch is triggered.
A dispatch gate (harness.dispatch.gate.require_authorization) independently enforces
that no transport call proceeds without this event, even if called out-of-band.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from harness.api.models import AuthorizeRequest, MissionResponse, MissionStatus
from harness.api.routes import _dispatch_mission
from harness.audit import logger as audit_module

auth_router = APIRouter()
logger = logging.getLogger(__name__)


@auth_router.post(
    "/authorize/{mission_id}",
    response_model=MissionResponse,
    summary="Authorize or reject a validated mission plan",
)
async def authorize_mission(
    mission_id: str,
    body: AuthorizeRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Human authorization gate (REQ-AUTH-01/02).

    - Mission must be in pending_authorization state (validator verdict ACCEPTED).
    - Returns HTTP 409 if the plan is in any other state.
    - On approval: records authorization event to the audit log, then triggers dispatch.
    - On rejection: marks the mission failed; no dispatch occurs.
    """
    missions: dict = request.app.state.missions
    if mission_id not in missions:
        raise HTTPException(status_code=404, detail=f"Mission '{mission_id}' not found")

    mission = missions[mission_id]

    if mission.status == MissionStatus.planning:
        raise HTTPException(
            status_code=409,
            detail="Mission is still being planned; try again shortly",
        )

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

    # Write authorization event to the audit log BEFORE triggering dispatch.
    # The dispatch gate (require_authorization) reads this event to validate the call.
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
