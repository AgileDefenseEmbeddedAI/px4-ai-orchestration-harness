"""
Audit replay tests.

Verifies that events written to the immutable JSONL audit log can be read
back with correct content and ordering, reproducing the original verdict.
"""

from unittest.mock import patch

import pytest

from harness.audit.logger import log_event, read_log


@pytest.fixture
def tmp_audit(tmp_path):
    with patch("harness.audit.logger.MISSIONS_DIR", tmp_path):
        yield tmp_path


def test_audit_log_roundtrip(tmp_audit):
    """Events written to the audit log must be readable back in insertion order."""
    mission_id = "MSN-AUDTEST1"
    events = [
        ("intent_received", {"text": "Scout Alpha-7 with UAV"}),
        ("plan_generated", {"vehicle_count": 1, "waypoint_count": 2}),
        ("validation_passed", {"errors": []}),
        ("authorized", {"operator": "SIERRA-6"}),
        ("dispatch_started", {"transport": "ros2"}),
        ("dispatch_complete", {"action_count": 2}),
    ]

    for event_type, payload in events:
        log_event(mission_id, event_type, payload)

    records = read_log(mission_id)
    assert len(records) == len(events)
    for record, (event_type, _) in zip(records, events):
        assert record["event"] == event_type
        assert record["mission_id"] == mission_id
        assert "ts" in record


def test_audit_replay_verdict_reproduction(tmp_audit):
    """Replaying a validation event reproduces the original verdict faithfully."""
    mission_id = "MSN-REPLAY01"
    validation_result = {
        "is_valid": False,
        "errors": ["Vehicle UAV-1 has no RTL waypoint (require_rtl is true)"],
    }

    log_event(mission_id, "validation_failed", validation_result)
    records = read_log(mission_id)

    assert len(records) == 1
    replayed = records[0]["payload"]
    assert replayed["is_valid"] == validation_result["is_valid"]
    assert replayed["errors"] == validation_result["errors"]


def test_read_log_empty_for_unknown_mission(tmp_audit):
    """Reading the log for a non-existent mission returns an empty list."""
    assert read_log("MSN-DOESNTEXIST") == []


def test_audit_log_append_only(tmp_audit):
    """Subsequent writes append to the log — no overwrite of prior records."""
    mission_id = "MSN-APPEND01"
    log_event(mission_id, "event_1", {"seq": 1})
    log_event(mission_id, "event_2", {"seq": 2})
    log_event(mission_id, "event_3", {"seq": 3})

    records = read_log(mission_id)
    assert len(records) == 3
    assert [r["event"] for r in records] == ["event_1", "event_2", "event_3"]


def test_audit_payload_preserved(tmp_audit):
    """Complex nested payloads are preserved through the JSONL round-trip."""
    mission_id = "MSN-PAYLOAD1"
    payload = {
        "nested": {"key": "value", "list": [1, 2, 3]},
        "unicode": "Alpha-α",
        "number": 3.14159,
    }
    log_event(mission_id, "complex_event", payload)

    records = read_log(mission_id)
    assert records[0]["payload"] == payload
