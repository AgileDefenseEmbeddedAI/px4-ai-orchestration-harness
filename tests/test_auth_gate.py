"""
Tests for the authorization gate and authorization screen.

Acceptance criteria:
- Calling the dispatch gate without a recorded authorization event raises UnauthorizedDispatchError.
- GET /ui/authorize/{id} renders all contingency ladder rungs present in the plan.
- POST /authorize/{id} on a REJECTED (validation_failed) plan returns HTTP 409.
- Authorization event is written to the audit log before dispatch is triggered.
"""

import pytest
from fastapi.testclient import TestClient

from harness.api.models import (
    Constraints,
    ContingencyRung,
    MIG,
    MissionResponse,
    MissionStatus,
    Vehicle,
    VehicleType,
    Waypoint,
)
from harness.dispatch.gate import UnauthorizedDispatchError, require_authorization


# ---------------------------------------------------------------------------
# Dispatch gate unit tests
# ---------------------------------------------------------------------------


def test_require_authorization_no_event():
    """Calling require_authorization for a mission with no audit log raises UnauthorizedDispatchError."""
    with pytest.raises(UnauthorizedDispatchError):
        require_authorization("MSN-NOAUTH-GATE-TEST-99")


def test_require_authorization_passes_with_event(tmp_path, monkeypatch):
    """require_authorization does not raise when an authorization_granted event exists."""
    import json
    from datetime import datetime, timezone

    from harness.audit import logger as audit_module

    # Redirect audit writes to a temp directory
    monkeypatch.setattr(audit_module, "MISSIONS_DIR", tmp_path)

    mission_id = "MSN-AUTHGATE-OK"
    audit_module.log_event(mission_id, "authorization_granted", {"operator": "SIERRA-6"})

    # Should not raise
    require_authorization(mission_id)


# ---------------------------------------------------------------------------
# POST /authorize — REJECTED plan returns 409
# ---------------------------------------------------------------------------


def test_authorize_rejected_plan_returns_409(app_client: TestClient):
    """POST /authorize on a validation_failed mission must return HTTP 409."""
    mission_id = "MSN-REJGATE01"
    app_client.app.state.missions[mission_id] = MissionResponse(
        mission_id=mission_id,
        status=MissionStatus.validation_failed,
        validation_errors=["Waypoint WP-1 exceeds max altitude"],
    )

    resp = app_client.post(
        f"/authorize/{mission_id}",
        json={"authorized": True, "operator": "SIERRA-6"},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Authorization event written before dispatch
# ---------------------------------------------------------------------------


def test_auth_event_written_before_dispatch(app_client: TestClient, tmp_path, monkeypatch):
    """authorization_granted is logged to the audit JSONL before dispatch is triggered."""
    from harness.audit import logger as audit_module

    monkeypatch.setattr(audit_module, "MISSIONS_DIR", tmp_path)

    mission_id = "MSN-AUDITORDER"
    mig = MIG(
        mission_id=mission_id,
        intent="Verify audit event ordering",
        vehicles=[
            Vehicle(
                id="UAV-1",
                vehicle_type=VehicleType.multirotor,
                sitl_target="gz_x500",
                mavlink_sysid=1,
                waypoints=["WP-1", "WP-RTL"],
            )
        ],
        waypoints=[
            Waypoint(id="WP-1", lat=35.1490, lon=-79.0100, alt_m=50.0, role="survey"),
            Waypoint(id="WP-RTL", lat=35.1400, lon=-79.0110, alt_m=30.0, role="rtl"),
        ],
        constraints=Constraints(max_alt_m=120.0, min_alt_m=5.0, require_rtl=True),
        status=MissionStatus.pending_authorization,
    )
    app_client.app.state.missions[mission_id] = MissionResponse(
        mission_id=mission_id,
        status=MissionStatus.pending_authorization,
        mig=mig,
    )

    resp = app_client.post(
        f"/authorize/{mission_id}",
        json={"authorized": True, "operator": "SIERRA-6"},
    )
    assert resp.status_code == 200

    entries = audit_module.read_log(mission_id)
    event_types = [e["event"] for e in entries]
    assert "authorization_granted" in event_types

    auth_idx = event_types.index("authorization_granted")
    dispatch_idxes = [i for i, e in enumerate(event_types) if "dispatch" in e]
    # All dispatch events must come after the authorization event
    for di in dispatch_idxes:
        assert di > auth_idx, "Dispatch event appeared before authorization_granted"


# ---------------------------------------------------------------------------
# UI template renders contingency ladder
# ---------------------------------------------------------------------------


def test_authorize_template_renders_contingency_ladder(app_client: TestClient):
    """GET /ui/authorize/{id} renders all contingency ladder rungs present in the MIG."""
    mission_id = "MSN-CONTLADDER"
    mig = MIG(
        mission_id=mission_id,
        intent="Test contingency ladder rendering",
        vehicles=[
            Vehicle(
                id="UAV-1",
                vehicle_type=VehicleType.multirotor,
                sitl_target="gz_x500",
                mavlink_sysid=1,
                waypoints=["WP-1", "WP-RTL"],
            )
        ],
        waypoints=[
            Waypoint(id="WP-1", lat=35.1490, lon=-79.0100, alt_m=50.0, role="survey"),
            Waypoint(id="WP-RTL", lat=35.1400, lon=-79.0110, alt_m=30.0, role="rtl"),
        ],
        constraints=Constraints(max_alt_m=120.0, min_alt_m=5.0, require_rtl=True),
        contingency_ladder=[
            ContingencyRung(priority=1, trigger="link_loss_5s", action="hold_position", description="Hold if comms lost 5s"),
            ContingencyRung(priority=2, trigger="link_loss_30s", action="return_to_launch", description="RTL if comms lost 30s"),
            ContingencyRung(priority=3, trigger="geofence_breach", action="return_to_launch", description="RTL on geofence breach"),
        ],
        status=MissionStatus.pending_authorization,
    )
    app_client.app.state.missions[mission_id] = MissionResponse(
        mission_id=mission_id,
        status=MissionStatus.pending_authorization,
        mig=mig,
    )

    resp = app_client.get(f"/ui/authorize/{mission_id}")
    assert resp.status_code == 200
    html = resp.text

    # All three contingency trigger names must appear in the rendered page
    assert "link_loss_5s" in html
    assert "link_loss_30s" in html
    assert "geofence_breach" in html

    # Actions must be present
    assert "hold_position" in html
    assert "return_to_launch" in html


def test_authorize_template_disabled_button_for_rejected_plan(app_client: TestClient):
    """GET /ui/authorize/{id} renders the Authorize button as disabled when verdict is REJECT."""
    mission_id = "MSN-REJECTBTN"
    app_client.app.state.missions[mission_id] = MissionResponse(
        mission_id=mission_id,
        status=MissionStatus.validation_failed,
        validation_errors=["Waypoint WP-99 is outside the geofence"],
    )

    resp = app_client.get(f"/ui/authorize/{mission_id}")
    assert resp.status_code == 200
    html = resp.text

    # The Authorize & Dispatch button must be rendered with disabled attribute
    assert "Authorize" in html
    assert "disabled" in html
