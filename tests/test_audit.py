"""
Tests for the immutable JSONL audit logger, replay tool, and query CLI.

(a) hash chain is valid after 10 appended events
(b) any in-place mutation of a log line breaks the hash check
(c) replay reproduces identical verdict for a stored mission
(d) query returns correct events for a known fixture
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from harness.api.models import (
    Constraints,
    MIG,
    MissionStatus,
    Vehicle,
    VehicleType,
    Waypoint,
)
from harness.audit.logger import log_event, read_log, verify_chain, VALIDATOR_VERSION
from harness.audit.replay import replay
from harness.audit.query import query
from harness.validator.constraint_checker import validate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GEOFENCE = [
    [35.1200, -79.0500],
    [35.1200, -78.9700],
    [35.1700, -78.9700],
    [35.1700, -79.0500],
]

CONSTRAINTS_CONFIG = {
    "geofence_polygon": GEOFENCE,
    "max_alt_m": 120.0,
    "min_alt_m": 5.0,
    "require_rtl": True,
}


def _make_mig(mission_id: str = "MSN-AUDIT001") -> MIG:
    return MIG(
        version="1.0",
        mission_id=mission_id,
        created_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        intent="Scout Alpha-7 with UAV",
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
        constraints=Constraints(
            geofence_polygon=GEOFENCE,
            max_alt_m=120.0,
            min_alt_m=5.0,
            require_rtl=True,
            max_range_m=5000.0,
        ),
        status=MissionStatus.pending_authorization,
        validation_errors=[],
    )


# ---------------------------------------------------------------------------
# (a) Hash chain is valid after 10 appended events
# ---------------------------------------------------------------------------


def test_hash_chain_valid_after_ten_events(tmp_path: Path):
    mission_id = "MSN-CHAIN001"
    for i in range(10):
        log_event(mission_id, "intent_received", {"seq": i}, missions_dir=tmp_path)

    is_valid, errors = verify_chain(mission_id, missions_dir=tmp_path)
    assert is_valid, f"Chain should be valid; errors: {errors}"
    assert errors == []

    records = read_log(mission_id, missions_dir=tmp_path)
    assert len(records) == 10
    # Every record must carry a _hash field
    for rec in records:
        assert "_hash" in rec
        assert len(rec["_hash"]) == 64  # SHA-256 hex digest


# ---------------------------------------------------------------------------
# (b) Any in-place mutation of a log line breaks the hash check
# ---------------------------------------------------------------------------


def test_hash_chain_mutation_detected(tmp_path: Path):
    mission_id = "MSN-MUTATE01"
    for i in range(5):
        log_event(mission_id, "intent_received", {"seq": i}, missions_dir=tmp_path)

    log_file = tmp_path / f"{mission_id}.jsonl"
    lines = log_file.read_text().splitlines()

    # Mutate the payload of the third line
    third = json.loads(lines[2])
    third["payload"]["seq"] = 999  # tamper with a value
    lines[2] = json.dumps(third)
    log_file.write_text("\n".join(lines) + "\n")

    is_valid, errors = verify_chain(mission_id, missions_dir=tmp_path)
    assert not is_valid, "Mutated log should fail hash verification"
    assert len(errors) >= 1
    # Lines 3+ should all report mismatch because the chain is broken at line 3
    assert any("3" in err or "Line 3" in err for err in errors)


# ---------------------------------------------------------------------------
# (c) Replay reproduces identical verdict
# ---------------------------------------------------------------------------


def test_replay_reproduces_verdict(tmp_path: Path):
    mission_id = "MSN-REPLAY01"
    mig = _make_mig(mission_id)

    is_valid, errors = validate(mig, CONSTRAINTS_CONFIG)

    # Write the events that the harness would write during a real run
    log_event(mission_id, "intent_received", {"intent": mig.intent}, missions_dir=tmp_path)
    log_event(
        mission_id,
        "plan_generated",
        {"mig": mig.model_dump(mode="json"), "validator_version": VALIDATOR_VERSION},
        missions_dir=tmp_path,
    )
    log_event(
        mission_id,
        "verdict_issued",
        {
            "is_valid": is_valid,
            "errors": errors,
            "validator_version": VALIDATOR_VERSION,
            "constraints_used": CONSTRAINTS_CONFIG,
        },
        missions_dir=tmp_path,
    )

    result = replay(mission_id, missions_dir=tmp_path, verbose=False)

    assert result["chain_valid"], f"Chain should be valid; errors: {result['chain_errors']}"
    assert result["verdict_match"] is True, (
        f"Replayed verdict should match stored verdict.\n"
        f"  stored: {result['stored_verdict']}\n"
        f"  replayed: {result['replayed_verdict']}"
    )


# ---------------------------------------------------------------------------
# (d) Query returns correct events for a known fixture
# ---------------------------------------------------------------------------


def test_query_returns_correct_events_for_vehicle(tmp_path: Path):
    mission_id = "MSN-QUERY001"

    # Causal chain events
    log_event(mission_id, "intent_received", {"intent": "Scout grid Alpha-7"}, missions_dir=tmp_path)
    log_event(
        mission_id,
        "verdict_issued",
        {"is_valid": True, "errors": [], "validator_version": VALIDATOR_VERSION, "constraints_used": {}},
        missions_dir=tmp_path,
    )
    log_event(
        mission_id,
        "authorization_recorded",
        {"operator": "SIERRA-6", "decision": "granted"},
        missions_dir=tmp_path,
    )

    # Vehicle-specific dispatch commands
    log_event(
        mission_id,
        "dispatch_command",
        {"vehicle_id": "UAV-1", "transport": "ros2", "action_count": 3, "result": "ok"},
        missions_dir=tmp_path,
    )
    log_event(
        mission_id,
        "dispatch_command",
        {"vehicle_id": "GND-1", "transport": "ros2", "action_count": 2, "result": "ok"},
        missions_dir=tmp_path,
    )
    log_event(
        mission_id,
        "dispatch_command",
        {"vehicle_id": "UAV-1", "transport": "mavlink2", "action_count": 3, "result": "ok"},
        missions_dir=tmp_path,
    )

    results = query(mission_id, vehicle_id="UAV-1", missions_dir=tmp_path)

    event_types = [r.get("event_type") for r in results]

    # Should include causal chain anchors
    assert "intent_received" in event_types
    assert "authorization_recorded" in event_types

    # Should include UAV-1's dispatch_command events
    uav_dispatch = [
        r for r in results
        if r.get("event_type") == "dispatch_command"
        and r.get("payload", {}).get("vehicle_id") == "UAV-1"
    ]
    assert len(uav_dispatch) == 2, f"Expected 2 UAV-1 dispatch_command events, got {len(uav_dispatch)}"

    # Should NOT include GND-1's event
    gnd_dispatch = [
        r for r in results
        if r.get("event_type") == "dispatch_command"
        and r.get("payload", {}).get("vehicle_id") == "GND-1"
    ]
    assert len(gnd_dispatch) == 0, "GND-1 events should not appear in UAV-1 query"
