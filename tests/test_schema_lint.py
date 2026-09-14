"""
Schema lint tests.

Validates that all JSON Schema files in schemas/ are syntactically valid
JSON and structurally valid JSON Schema Draft-07.
"""

import json
from pathlib import Path

import jsonschema
import pytest

SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


def _schema_files():
    return list(sorted(SCHEMAS_DIR.glob("*.json")))


@pytest.mark.parametrize("schema_file", _schema_files(), ids=lambda p: p.name)
def test_schema_is_valid_json(schema_file):
    """Each schema file must be parseable as valid JSON."""
    with open(schema_file) as f:
        data = json.load(f)
    assert isinstance(data, dict), f"{schema_file.name} must be a JSON object"


@pytest.mark.parametrize("schema_file", _schema_files(), ids=lambda p: p.name)
def test_schema_is_valid_draft07(schema_file):
    """Each schema must be a valid JSON Schema Draft-07 document."""
    with open(schema_file) as f:
        data = json.load(f)
    try:
        jsonschema.Draft7Validator.check_schema(data)
    except jsonschema.SchemaError as exc:
        pytest.fail(f"{schema_file.name} is not a valid Draft-07 schema: {exc.message}")


def test_mig_schema_exists():
    assert (SCHEMAS_DIR / "mig.json").exists(), "schemas/mig.json is missing"


def test_val_schema_exists():
    assert (SCHEMAS_DIR / "val.json").exists(), "schemas/val.json is missing"


def test_verdict_schema_exists():
    assert (SCHEMAS_DIR / "verdict.v1.json").exists(), "schemas/verdict.v1.json is missing"


def test_mig_schema_declares_draft07():
    with open(SCHEMAS_DIR / "mig.json") as f:
        data = json.load(f)
    assert "draft-07" in data.get("$schema", "").lower(), (
        "schemas/mig.json must declare JSON Schema Draft-07"
    )


def test_verdict_schema_required_fields():
    """verdict.v1.json must require mission_id, is_valid, errors, and checked_at."""
    with open(SCHEMAS_DIR / "verdict.v1.json") as f:
        data = json.load(f)
    required = set(data.get("required", []))
    assert {"mission_id", "is_valid", "errors", "checked_at"}.issubset(required)
