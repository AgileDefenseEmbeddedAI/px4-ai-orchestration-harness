"""
Integration tests for the FastAPI routes.

Uses FastAPI's TestClient (synchronous). Background tasks complete before
the TestClient returns a response, so planning/validation results are visible
immediately in subsequent GET calls.
"""

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# POST /intent
# ---------------------------------------------------------------------------


def test_post_intent_creates_mission(app_client: TestClient, sample_intent: str):
    """POST /intent should create a mission and return a mission_id."""
    response = app_client.post("/intent", json={"text": sample_intent})
    assert response.status_code == 200
    data = response.json()
    assert "mission_id" in data
    assert data["mission_id"].startswith("MSN-")
    assert "status" in data


def test_post_intent_too_short(app_client: TestClient):
    """POST /intent with text shorter than 10 chars should return 422."""
    response = app_client.post("/intent", json={"text": "short"})
    assert response.status_code == 422


def test_post_intent_missing_text(app_client: TestClient):
    """POST /intent with no body should return 422."""
    response = app_client.post("/intent", json={})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /plan/{mission_id}
# ---------------------------------------------------------------------------


def test_get_plan_not_found(app_client: TestClient):
    """GET /plan for an unknown mission ID should return 404."""
    response = app_client.get("/plan/MSN-DOESNTEXIST")
    assert response.status_code == 404


def test_get_plan_returns_mission(app_client: TestClient, sample_intent: str):
    """GET /plan/{id} should return the mission state."""
    post_resp = app_client.post("/intent", json={"text": sample_intent})
    mission_id = post_resp.json()["mission_id"]

    get_resp = app_client.get(f"/plan/{mission_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["mission_id"] == mission_id
    assert "status" in data


# ---------------------------------------------------------------------------
# GET /missions
# ---------------------------------------------------------------------------


def test_get_missions_list(app_client: TestClient):
    """GET /missions should return a list (empty or not)."""
    response = app_client.get("/missions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_missions_includes_created(app_client: TestClient, sample_intent: str):
    """After creating a mission, it should appear in GET /missions."""
    post_resp = app_client.post("/intent", json={"text": sample_intent})
    mission_id = post_resp.json()["mission_id"]

    list_resp = app_client.get("/missions")
    assert list_resp.status_code == 200
    ids = [m["mission_id"] for m in list_resp.json()]
    assert mission_id in ids


# ---------------------------------------------------------------------------
# POST /authorize/{mission_id}
# ---------------------------------------------------------------------------


def test_authorize_unknown_mission(app_client: TestClient):
    """POST /authorize on a non-existent mission should return 404."""
    response = app_client.post(
        "/authorize/MSN-DOESNTEXIST",
        json={"authorized": True, "operator": "SIERRA-6"},
    )
    assert response.status_code == 404


def test_authorize_still_planning_returns_409(app_client: TestClient):
    """
    Attempting to authorize a mission that is in 'planning' state
    (before background task runs) should return 409.

    Note: with TestClient, background tasks run synchronously, so planning
    completes before this test can reliably catch the 'planning' state.
    This test verifies the 409 path exists — it may not be reachable in the
    synchronous test harness, so we accept 200 or 409.
    """
    # Inject a mission directly into state in 'planning' status
    from harness.api.models import MissionResponse, MissionStatus

    mission_id = "MSN-PLANTEST"
    app_client.app.state.missions[mission_id] = MissionResponse(
        mission_id=mission_id,
        status=MissionStatus.planning,
    )

    response = app_client.post(
        f"/authorize/{mission_id}",
        json={"authorized": True, "operator": "SIERRA-6"},
    )
    assert response.status_code == 409


def test_authorize_validation_failed_returns_409(app_client: TestClient):
    """Attempting to authorize a mission that failed validation should return 409."""
    from harness.api.models import MissionResponse, MissionStatus

    mission_id = "MSN-VALFAIL1"
    app_client.app.state.missions[mission_id] = MissionResponse(
        mission_id=mission_id,
        status=MissionStatus.validation_failed,
        validation_errors=["Waypoint WP-1 is outside the geofence"],
    )

    response = app_client.post(
        f"/authorize/{mission_id}",
        json={"authorized": True, "operator": "SIERRA-6"},
    )
    assert response.status_code == 409


def test_authorize_pending_mission(app_client: TestClient):
    """Authorizing a pending_authorization mission should succeed."""
    from harness.api.models import (
        Constraints,
        MIG,
        MissionResponse,
        MissionStatus,
        Vehicle,
        VehicleType,
        Waypoint,
    )

    mission_id = "MSN-AUTHTEST"
    mig = MIG(
        mission_id=mission_id,
        intent="Test authorization flow",
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

    response = app_client.post(
        f"/authorize/{mission_id}",
        json={"authorized": True, "operator": "SIERRA-6"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["authorized_by"] == "SIERRA-6"
    assert data["status"] in ("authorized", "dispatching", "dispatched")


# ---------------------------------------------------------------------------
# GET /audit/{mission_id}
# ---------------------------------------------------------------------------


def test_get_audit_returns_list(app_client: TestClient, sample_intent: str):
    """GET /audit/{id} should return a list (may be empty for new missions)."""
    post_resp = app_client.post("/intent", json={"text": sample_intent})
    mission_id = post_resp.json()["mission_id"]

    audit_resp = app_client.get(f"/audit/{mission_id}")
    assert audit_resp.status_code == 200
    assert isinstance(audit_resp.json(), list)
