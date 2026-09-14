"""
Unit tests for the deterministic validator engine and constraint checker.

All tests are synchronous — the validator never calls the LLM.
"""

import ast
import pathlib

import pytest
import yaml

from harness.api.models import (
    Constraints,
    MIG,
    MissionStatus,
    Vehicle,
    VehicleType,
    Waypoint,
)
from harness.validator import engine
from harness.validator.constraint_checker import validate

# ---------------------------------------------------------------------------
# Shared test data
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
    "min_horizontal_sep_m": 50.0,
    "min_vertical_sep_m": 10.0,
}


def _base_mig(**overrides) -> MIG:
    """Return a minimal valid MIG, optionally overriding fields."""
    defaults = dict(
        version="1.0",
        mission_id="MSN-TEST0001",
        intent="Test mission",
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
        status=MissionStatus.planning,
        validation_errors=[],
    )
    defaults.update(overrides)
    return MIG(**defaults)


# ---------------------------------------------------------------------------
# Legacy constraint_checker tests (backward compatibility)
# ---------------------------------------------------------------------------


def test_valid_plan_passes():
    mig = _base_mig()
    is_valid, errors = validate(mig, CONSTRAINTS_CONFIG)
    assert is_valid is True
    assert errors == []


def test_altitude_too_high():
    mig = _base_mig(
        waypoints=[
            Waypoint(id="WP-1", lat=35.1490, lon=-79.0100, alt_m=999.0, role="survey"),
            Waypoint(id="WP-RTL", lat=35.1400, lon=-79.0110, alt_m=30.0, role="rtl"),
        ]
    )
    is_valid, errors = validate(mig, CONSTRAINTS_CONFIG)
    assert is_valid is False
    assert any("999" in e or "altitude" in e.lower() for e in errors)


def test_altitude_too_low_for_aerial():
    mig = _base_mig(
        waypoints=[
            Waypoint(id="WP-1", lat=35.1490, lon=-79.0100, alt_m=1.0, role="survey"),
            Waypoint(id="WP-RTL", lat=35.1400, lon=-79.0110, alt_m=30.0, role="rtl"),
        ]
    )
    is_valid, errors = validate(mig, CONSTRAINTS_CONFIG)
    assert is_valid is False
    assert any("1.0" in e or "below" in e.lower() or "minimum" in e.lower() for e in errors)


def test_rover_at_zero_alt_passes():
    mig = _base_mig(
        vehicles=[
            Vehicle(
                id="GND-1",
                vehicle_type=VehicleType.rover,
                sitl_target="gz_rover_ackermann",
                mavlink_sysid=1,
                waypoints=["WP-1", "WP-RTL"],
            )
        ],
        waypoints=[
            Waypoint(id="WP-1", lat=35.1490, lon=-79.0100, alt_m=0.0, role="survey"),
            Waypoint(id="WP-RTL", lat=35.1400, lon=-79.0110, alt_m=0.0, role="rtl"),
        ],
    )
    is_valid, errors = validate(mig, CONSTRAINTS_CONFIG)
    assert is_valid is True, f"Unexpected errors: {errors}"


def test_no_rtl_fails():
    mig = _base_mig(
        waypoints=[
            Waypoint(id="WP-1", lat=35.1490, lon=-79.0100, alt_m=50.0, role="survey"),
        ],
        vehicles=[
            Vehicle(
                id="UAV-1",
                vehicle_type=VehicleType.multirotor,
                sitl_target="gz_x500",
                mavlink_sysid=1,
                waypoints=["WP-1"],
            )
        ],
    )
    is_valid, errors = validate(mig, CONSTRAINTS_CONFIG)
    assert is_valid is False
    assert any("RTL" in e or "rtl" in e.lower() for e in errors)


def test_out_of_bounds_fails():
    mig = _base_mig(
        waypoints=[
            Waypoint(id="WP-1", lat=40.7128, lon=-74.0060, alt_m=50.0, role="survey"),
            Waypoint(id="WP-RTL", lat=40.7000, lon=-74.0000, alt_m=30.0, role="rtl"),
        ]
    )
    is_valid, errors = validate(mig, CONSTRAINTS_CONFIG)
    assert is_valid is False
    assert any("geofence" in e.lower() or "outside" in e.lower() for e in errors)


def test_empty_vehicles_fails():
    mig = _base_mig(vehicles=[], waypoints=[])
    is_valid, errors = validate(mig, CONSTRAINTS_CONFIG)
    assert is_valid is False
    assert any("vehicle" in e.lower() for e in errors)


def test_unknown_waypoint_reference_fails():
    mig = _base_mig(
        vehicles=[
            Vehicle(
                id="UAV-1",
                vehicle_type=VehicleType.multirotor,
                sitl_target="gz_x500",
                mavlink_sysid=1,
                waypoints=["WP-1", "WP-MISSING", "WP-RTL"],
            )
        ],
    )
    is_valid, errors = validate(mig, CONSTRAINTS_CONFIG)
    assert is_valid is False
    assert any("WP-MISSING" in e for e in errors)


def test_no_geofence_config_skips_check():
    mig = _base_mig(
        waypoints=[
            Waypoint(id="WP-1", lat=40.7128, lon=-74.0060, alt_m=50.0, role="survey"),
            Waypoint(id="WP-RTL", lat=40.7000, lon=-74.0000, alt_m=30.0, role="rtl"),
        ]
    )
    is_valid, errors = validate(mig, {})
    assert not any("geofence" in e.lower() for e in errors)


# ---------------------------------------------------------------------------
# Engine tests
# ---------------------------------------------------------------------------


def test_engine_valid_plan_accepted():
    """A well-formed four-waypoint plan within all constraints is accepted."""
    mig = MIG(
        version="1.0",
        mission_id="MSN-FOURV001",
        intent="Scout and secure with mixed fleet",
        vehicles=[
            Vehicle(id="UAV-1", vehicle_type=VehicleType.multirotor,
                    sitl_target="gz_x500", mavlink_sysid=1,
                    waypoints=["WP-1", "WP-2", "WP-RTL-1"]),
            Vehicle(id="UAV-2", vehicle_type=VehicleType.multirotor,
                    sitl_target="gz_x500", mavlink_sysid=2,
                    waypoints=["WP-3", "WP-RTL-2"]),
            Vehicle(id="GND-1", vehicle_type=VehicleType.rover,
                    sitl_target="gz_rover_ackermann", mavlink_sysid=3,
                    waypoints=["WP-4", "WP-RTL-3"]),
            Vehicle(id="GND-2", vehicle_type=VehicleType.rover,
                    sitl_target="gz_rover_ackermann", mavlink_sysid=4,
                    waypoints=["WP-5", "WP-RTL-4"]),
        ],
        waypoints=[
            Waypoint(id="WP-1",    lat=35.1490, lon=-79.0100, alt_m=50.0, role="survey"),
            Waypoint(id="WP-2",    lat=35.1510, lon=-79.0080, alt_m=50.0, role="loiter"),
            Waypoint(id="WP-RTL-1",lat=35.1400, lon=-79.0110, alt_m=30.0, role="rtl"),
            Waypoint(id="WP-3",    lat=35.1530, lon=-79.0060, alt_m=70.0, role="survey"),
            Waypoint(id="WP-RTL-2",lat=35.1400, lon=-79.0110, alt_m=30.0, role="rtl"),
            Waypoint(id="WP-4",    lat=35.1420, lon=-79.0120, alt_m=0.0,  role="survey"),
            Waypoint(id="WP-RTL-3",lat=35.1400, lon=-79.0110, alt_m=0.0,  role="rtl"),
            Waypoint(id="WP-5",    lat=35.1440, lon=-79.0090, alt_m=0.0,  role="perimeter"),
            Waypoint(id="WP-RTL-4",lat=35.1400, lon=-79.0110, alt_m=0.0,  role="rtl"),
        ],
        constraints=Constraints(
            geofence_polygon=GEOFENCE, max_alt_m=120.0, min_alt_m=5.0,
            require_rtl=True, max_range_m=5000.0,
        ),
        status=MissionStatus.planning,
        validation_errors=[],
    )
    verdict = engine.run(mig, CONSTRAINTS_CONFIG)
    assert verdict["result"] == "accept", f"Unexpected violations: {verdict['violations']}"
    assert verdict["violations"] == []


def test_engine_determinism():
    """Running the engine twice on the same MIG produces identical output."""
    mig = _base_mig()
    verdict1 = engine.run(mig, CONSTRAINTS_CONFIG)
    verdict2 = engine.run(mig, CONSTRAINTS_CONFIG)
    assert verdict1 == verdict2


def test_engine_verdict_structure():
    """Verdict dict has required keys matching schemas/verdict.v1.json."""
    mig = _base_mig()
    verdict = engine.run(mig, CONSTRAINTS_CONFIG)
    assert "plan_id" in verdict
    assert "validator_version" in verdict
    assert "result" in verdict
    assert "violations" in verdict
    assert verdict["plan_id"] == mig.mission_id
    assert verdict["result"] in ("accept", "reject")


def test_engine_rover_nonzero_altitude_rejected():
    mig = _base_mig(
        vehicles=[
            Vehicle(id="GND-1", vehicle_type=VehicleType.rover,
                    sitl_target="gz_rover_ackermann", mavlink_sysid=1,
                    waypoints=["WP-1", "WP-RTL"])
        ],
        waypoints=[
            Waypoint(id="WP-1", lat=35.1490, lon=-79.0100, alt_m=50.0, role="survey"),
            Waypoint(id="WP-RTL", lat=35.1400, lon=-79.0110, alt_m=0.0, role="rtl"),
        ],
    )
    verdict = engine.run(mig, CONSTRAINTS_CONFIG)
    assert verdict["result"] == "reject"
    ids = [v["constraint_id"] for v in verdict["violations"]]
    assert "VIOL-ROVER-ALT" in ids


def test_engine_forbidden_mav_cmd_rejected():
    mig = _base_mig(
        vehicles=[
            Vehicle(id="GND-1", vehicle_type=VehicleType.rover,
                    sitl_target="gz_rover_ackermann", mavlink_sysid=1,
                    waypoints=["WP-1", "WP-RTL"])
        ],
        waypoints=[
            Waypoint(id="WP-1", lat=35.1490, lon=-79.0100, alt_m=0.0, role="survey",
                     mav_cmd="MAV_CMD_NAV_TAKEOFF"),
            Waypoint(id="WP-RTL", lat=35.1400, lon=-79.0110, alt_m=0.0, role="rtl"),
        ],
    )
    verdict = engine.run(mig, CONSTRAINTS_CONFIG)
    assert verdict["result"] == "reject"
    ids = [v["constraint_id"] for v in verdict["violations"]]
    assert "VIOL-FORBIDDEN-CMD" in ids


def test_engine_out_of_order_timestamps_rejected():
    mig = _base_mig(
        waypoints=[
            Waypoint(id="WP-1", lat=35.1490, lon=-79.0100, alt_m=50.0,
                     role="survey", t_s=100.0),
            Waypoint(id="WP-RTL", lat=35.1400, lon=-79.0110, alt_m=30.0,
                     role="rtl", t_s=50.0),
        ]
    )
    verdict = engine.run(mig, CONSTRAINTS_CONFIG)
    assert verdict["result"] == "reject"
    ids = [v["constraint_id"] for v in verdict["violations"]]
    assert "VIOL-TIMESTAMP-ORDER" in ids


def test_engine_zero_duration_window_rejected():
    mig = _base_mig(
        waypoints=[
            Waypoint(id="WP-1", lat=35.1490, lon=-79.0100, alt_m=50.0,
                     role="survey", t_s=0.0),
            Waypoint(id="WP-RTL", lat=35.1400, lon=-79.0110, alt_m=30.0,
                     role="rtl", t_s=0.0),
        ]
    )
    verdict = engine.run(mig, CONSTRAINTS_CONFIG)
    assert verdict["result"] == "reject"
    ids = [v["constraint_id"] for v in verdict["violations"]]
    assert "VIOL-ZERO-DURATION" in ids


def test_engine_deconfliction_rejected():
    """Two vehicles within minimum separation at the same time are rejected."""
    mig = _base_mig(
        vehicles=[
            Vehicle(id="UAV-1", vehicle_type=VehicleType.multirotor,
                    sitl_target="gz_x500", mavlink_sysid=1,
                    waypoints=["WP-A1", "WP-RTL-1"]),
            Vehicle(id="UAV-2", vehicle_type=VehicleType.multirotor,
                    sitl_target="gz_x500", mavlink_sysid=2,
                    waypoints=["WP-A2", "WP-RTL-2"]),
        ],
        waypoints=[
            Waypoint(id="WP-A1", lat=35.1490, lon=-79.0100, alt_m=50.0,
                     role="survey", t_s=60.0),
            Waypoint(id="WP-A2", lat=35.1491, lon=-79.0101, alt_m=51.0,
                     role="survey", t_s=60.0),
            Waypoint(id="WP-RTL-1", lat=35.1400, lon=-79.0110, alt_m=30.0,
                     role="rtl", t_s=300.0),
            Waypoint(id="WP-RTL-2", lat=35.1400, lon=-79.0110, alt_m=30.0,
                     role="rtl", t_s=300.0),
        ],
    )
    verdict = engine.run(mig, CONSTRAINTS_CONFIG)
    assert verdict["result"] == "reject"
    ids = [v["constraint_id"] for v in verdict["violations"]]
    assert "VIOL-DECONFLICT" in ids


# ---------------------------------------------------------------------------
# Import graph enforcement
# ---------------------------------------------------------------------------


def test_engine_no_llm_imports():
    """engine.py must not import from harness.planner or any LLM client library."""
    engine_path = pathlib.Path("harness/validator/engine.py")
    tree = ast.parse(engine_path.read_text())

    forbidden_prefixes = ("harness.planner", "openai", "anthropic", "langchain")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in forbidden_prefixes:
                    assert not alias.name.startswith(prefix), (
                        f"engine.py must not import '{alias.name}' "
                        f"(matches forbidden prefix '{prefix}')"
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for prefix in forbidden_prefixes:
                assert not module.startswith(prefix), (
                    f"engine.py must not import from '{module}' "
                    f"(matches forbidden prefix '{prefix}')"
                )


# ---------------------------------------------------------------------------
# Adversarial corpus — all entries must be rejected
# ---------------------------------------------------------------------------

ADVERSARIAL_DIR = pathlib.Path("tests/adversarial")
CONSTRAINTS_FILE = pathlib.Path("config/constraints.yaml")


def _load_corpus_constraints() -> dict:
    with CONSTRAINTS_FILE.open() as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


@pytest.mark.parametrize("corpus_file", sorted(ADVERSARIAL_DIR.glob("*.yaml")))
def test_adversarial_corpus_rejected(corpus_file):
    """Every adversarial corpus entry must be rejected by the engine."""
    constraints = _load_corpus_constraints()
    with corpus_file.open() as fh:
        entry = yaml.safe_load(fh)

    mig = MIG(**entry["mig"])
    verdict = engine.run(mig, constraints)

    assert verdict["result"] == "reject", (
        f"Corpus entry '{corpus_file.name}' was accepted — expected rejection.\n"
        f"Violations: {verdict['violations']}"
    )

    # If the entry specifies an expected constraint id, verify it's present
    expected_error = entry.get("expected_error_contains", "")
    if expected_error:
        all_text = " ".join(
            v.get("constraint_id", "") + " " + v.get("description", "")
            for v in verdict["violations"]
        )
        assert expected_error in all_text, (
            f"Corpus entry '{corpus_file.name}' was rejected but expected "
            f"'{expected_error}' not found in violations:\n"
            f"{[v['constraint_id'] for v in verdict['violations']]}"
        )
