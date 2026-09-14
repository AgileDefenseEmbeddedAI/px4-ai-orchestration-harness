"""
Adversarial corpus gate.

Loads every YAML file from tests/adversarial/ and asserts that the
deterministic validator rejects it. All corpus entries MUST be rejected;
an accepted adversarial plan is a gate failure.
"""

from pathlib import Path

import pytest
import yaml

from harness.api.models import MIG
from harness.validator.constraint_checker import validate

ADVERSARIAL_DIR = Path(__file__).parent / "adversarial"

# Standard Fort Bragg geofence — used to evaluate geofence violations
_GEOFENCE = [
    [35.1200, -79.0500],
    [35.1200, -78.9700],
    [35.1700, -78.9700],
    [35.1700, -79.0500],
]

_CONSTRAINTS_CONFIG = {"geofence_polygon": _GEOFENCE}


def _load_cases():
    cases = []
    for yaml_file in sorted(ADVERSARIAL_DIR.glob("*.yaml")):
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        cases.append(pytest.param(yaml_file.name, data, id=yaml_file.stem))
    return cases


@pytest.mark.parametrize("filename,case", _load_cases())
def test_adversarial_case_is_rejected(filename, case):
    """Every corpus entry must be rejected by the deterministic validator."""
    mig = MIG(**case["mig"])
    is_valid, errors = validate(mig, _CONSTRAINTS_CONFIG)

    assert not is_valid, (
        f"CORPUS GATE FAILURE: {filename!r} was accepted but must be rejected. "
        f"Adversarial plans must always fail validation."
    )

    if expected := case.get("expected_error_contains"):
        assert any(expected.lower() in e.lower() for e in errors), (
            f"{filename!r}: expected error containing {expected!r}, got: {errors}"
        )


def test_corpus_count_minimum():
    """Corpus must have at least 8 entries to provide meaningful adversarial coverage."""
    corpus_files = list(ADVERSARIAL_DIR.glob("*.yaml"))
    count = len(corpus_files)
    assert count >= 8, (
        f"Adversarial corpus has only {count} entries; need >= 8. "
        "Add more adversarial test cases to tests/adversarial/."
    )
