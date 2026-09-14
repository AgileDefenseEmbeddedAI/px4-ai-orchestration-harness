#!/usr/bin/env python3
"""
Adversarial corpus validation script.

Loads every YAML file from tests/adversarial/, runs the deterministic validator
engine against each one, and asserts 100% rejection. Exits 0 on success, 1 on
any failure.

Usage:
    python scripts/validate_corpus.py
    make validate-corpus
"""

import sys
from pathlib import Path

import yaml

# Allow running from the repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.api.models import MIG  # noqa: E402
from harness.validator import engine  # noqa: E402

ADVERSARIAL_DIR = Path(__file__).parent.parent / "tests" / "adversarial"
CONSTRAINTS_FILE = Path(__file__).parent.parent / "config" / "constraints.yaml"


def load_constraints() -> dict:
    with CONSTRAINTS_FILE.open() as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def run_corpus(constraints: dict) -> bool:
    corpus_files = sorted(ADVERSARIAL_DIR.glob("*.yaml"))
    if not corpus_files:
        print("ERROR: No adversarial corpus files found in", ADVERSARIAL_DIR)
        return False

    passed = 0
    failed = 0

    for path in corpus_files:
        with path.open() as fh:
            entry = yaml.safe_load(fh)

        name = entry.get("name", path.stem)
        raw_mig = entry.get("mig", {})
        expected_error = entry.get("expected_error_contains", "")

        try:
            mig = MIG(**raw_mig)
        except Exception as exc:
            print(f"  FAIL  [{path.name}] Could not parse MIG: {exc}")
            failed += 1
            continue

        verdict = engine.run(mig, constraints)

        if verdict["result"] != "reject":
            print(f"  FAIL  [{path.name}] Expected rejection but got '{verdict['result']}': {name}")
            failed += 1
            continue

        # Optional: assert expected constraint_id appears in at least one violation
        if expected_error:
            descriptions = " ".join(
                v.get("constraint_id", "") + " " + v.get("description", "")
                for v in verdict.get("violations", [])
            )
            if expected_error not in descriptions:
                print(
                    f"  FAIL  [{path.name}] Rejected but expected error "
                    f"'{expected_error}' not found in violations:\n"
                    f"        {[v['constraint_id'] for v in verdict['violations']]}"
                )
                failed += 1
                continue

        constraint_ids = [v["constraint_id"] for v in verdict["violations"]]
        print(f"  PASS  [{path.name}] Rejected with {constraint_ids}: {name}")
        passed += 1

    print(f"\nCorpus result: {passed} passed, {failed} failed (of {passed + failed} entries)")
    return failed == 0


def main() -> int:
    constraints = load_constraints()
    print(f"Loaded constraints from {CONSTRAINTS_FILE}")
    print(f"Running adversarial corpus from {ADVERSARIAL_DIR}\n")
    ok = run_corpus(constraints)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
