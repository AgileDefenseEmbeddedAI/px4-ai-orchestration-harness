"""
Mission replay tool.

Reads a mission JSONL audit log, verifies the hash chain, re-runs the
deterministic validator against the stored plan artifact, and asserts the
verdict matches the stored verdict_issued event.
"""

from pathlib import Path
from typing import Any

from harness.audit.logger import MISSIONS_DIR, read_log, verify_chain
from harness.api.models import MIG
from harness.validator.constraint_checker import validate


def replay(
    mission_id: str,
    missions_dir: Path | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Replay a recorded mission from its JSONL audit log.

    Returns a dict with keys:
        chain_valid     - bool: True if hash chain is intact
        chain_errors    - list[str]: any hash violations found
        verdict_match   - bool | None: True if replayed verdict matches stored verdict;
                          None if the log lacks a verdict_issued event
        stored_verdict  - dict | None: the verdict from the original run
        replayed_verdict - dict | None: the verdict from the replay run
        timeline        - list[dict]: all events in order
    """
    records = read_log(mission_id, missions_dir)
    chain_ok, chain_errors = verify_chain(mission_id, missions_dir)

    result: dict[str, Any] = {
        "chain_valid": chain_ok,
        "chain_errors": chain_errors,
        "verdict_match": None,
        "stored_verdict": None,
        "replayed_verdict": None,
        "timeline": records,
    }

    if verbose:
        _print_timeline(mission_id, records, missions_dir)

    # Find plan_generated and verdict_issued events
    plan_payload: dict | None = None
    verdict_payload: dict | None = None

    for rec in records:
        et = rec.get("event_type", "")
        if et == "plan_generated":
            plan_payload = rec.get("payload", {})
        elif et == "verdict_issued":
            verdict_payload = rec.get("payload", {})

    if plan_payload is None or verdict_payload is None:
        if verbose:
            print("\n[replay] Missing plan_generated or verdict_issued event — skipping verdict check.")
        return result

    # Reconstruct MIG from stored artifact
    mig_data = plan_payload.get("mig")
    if mig_data is None:
        if verbose:
            print("\n[replay] plan_generated event has no 'mig' field — cannot replay.")
        return result

    try:
        mig = MIG.model_validate(mig_data)
    except Exception as exc:
        if verbose:
            print(f"\n[replay] Failed to reconstruct MIG: {exc}")
        return result

    # Use constraints stored in verdict_issued for deterministic replay
    constraints_used = verdict_payload.get("constraints_used", {})
    is_valid, errors = validate(mig, constraints_used)

    stored_is_valid = verdict_payload.get("is_valid")
    stored_errors = verdict_payload.get("errors", [])

    replayed = {"is_valid": is_valid, "errors": errors}
    stored = {"is_valid": stored_is_valid, "errors": stored_errors}

    verdict_match = (is_valid == stored_is_valid) and (sorted(errors) == sorted(stored_errors))

    result["verdict_match"] = verdict_match
    result["stored_verdict"] = stored
    result["replayed_verdict"] = replayed

    if verbose:
        _print_verdict_comparison(stored, replayed, verdict_match)

    return result


def _print_timeline(mission_id: str, records: list[dict], missions_dir: Path | None) -> None:
    d = missions_dir or MISSIONS_DIR
    log_path = d / f"{mission_id}.jsonl"

    print(f"=== Mission Replay: {mission_id} ===")
    print(f"Log file : {log_path.resolve()}")
    print(f"Events   : {len(records)}")
    print()

    for i, rec in enumerate(records, 1):
        ts = rec.get("ts", "unknown")
        et = rec.get("event_type", rec.get("event", "")).upper()
        print(f"[{i:02d}] {ts}  EVENT: {et}")
        payload = rec.get("payload", {})
        if isinstance(payload, dict):
            for key, val in payload.items():
                if key == "mig":
                    print(f"       {key}: <MIG object>")
                elif isinstance(val, (dict, list)) and len(str(val)) > 120:
                    print(f"       {key}: <{type(val).__name__}>")
                else:
                    print(f"       {key}: {val}")
        elif payload:
            print(f"       payload: {payload}")
        print()

    # Summary
    statuses = [r.get("event_type", r.get("event", "")) for r in records]
    if "dispatch_command" in statuses or "dispatch_complete" in statuses:
        print("Outcome: DISPATCHED")
    elif "authorization_recorded" in statuses:
        last_auth = next(
            (r for r in reversed(records) if r.get("event_type") == "authorization_recorded"),
            None,
        )
        if last_auth and last_auth.get("payload", {}).get("decision") == "rejected":
            print("Outcome: REJECTED")
        else:
            print("Outcome: AUTHORIZED")
    elif "verdict_issued" in statuses:
        last_verdict = next(
            (r for r in reversed(records) if r.get("event_type") == "verdict_issued"),
            None,
        )
        if last_verdict and not last_verdict.get("payload", {}).get("is_valid"):
            print("Outcome: VALIDATION FAILED")
        else:
            print("Outcome: PENDING AUTHORIZATION")
    else:
        last = statuses[-1] if statuses else "none"
        print(f"Outcome: INCOMPLETE (last event: {last})")


def _print_verdict_comparison(stored: dict, replayed: dict, match: bool) -> None:
    print()
    print("=== Verdict Comparison ===")
    print(f"Stored   is_valid: {stored['is_valid']}")
    print(f"Replayed is_valid: {replayed['is_valid']}")
    if stored["errors"]:
        print(f"Stored   errors  : {stored['errors']}")
    if replayed["errors"]:
        print(f"Replayed errors  : {replayed['errors']}")
    if match:
        print("RESULT: PASS — replayed verdict matches stored verdict")
    else:
        print("RESULT: FAIL — verdict mismatch detected")
