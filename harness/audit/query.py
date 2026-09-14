"""
Audit log query CLI.

Usage:
    python -m harness.audit.query --mission <id> [--vehicle <vid>] [--time <T>] [--action]

Scans the mission JSONL log and returns matching events with a causal chain
(intent → plan waypoint → dispatch command → telemetry).
"""

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

from harness.audit.logger import MISSIONS_DIR, read_log


_CAUSAL_CHAIN_TYPES = {
    "intent_received",
    "plan_generated",
    "verdict_issued",
    "authorization_recorded",
}

_TIME_WINDOW_SECONDS = 60


def _parse_time(t_str: str) -> datetime:
    try:
        dt = datetime.fromisoformat(t_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        raise ValueError(f"Invalid time format: {t_str!r}. Use ISO 8601 (e.g. 2026-01-01T12:00:00Z)")


def _event_references_vehicle(record: dict, vehicle_id: str) -> bool:
    payload = record.get("payload", {})
    if not isinstance(payload, dict):
        return False
    if payload.get("vehicle_id") == vehicle_id:
        return True
    # dispatch_command events can have vehicle_id nested
    val = payload.get("val", {})
    if isinstance(val, dict) and val.get("vehicle_id") == vehicle_id:
        return True
    return False


def query(
    mission_id: str,
    vehicle_id: str | None = None,
    time_str: str | None = None,
    show_action: bool = False,
    missions_dir: Path | None = None,
) -> list[dict]:
    """
    Return audit events for a mission, optionally filtered by vehicle and time.

    When vehicle_id is given, always prepends causal-chain events (intent,
    plan, verdict, authorization) so the caller can trace the full provenance.
    """
    records = read_log(mission_id, missions_dir)

    if not records:
        return []

    anchor_dt: datetime | None = None
    if time_str:
        anchor_dt = _parse_time(time_str)

    # Split records into causal-chain anchors and vehicle-specific events
    causal: list[dict] = []
    matched: list[dict] = []

    for rec in records:
        et = rec.get("event_type", "")
        ts_str = rec.get("ts", "")

        # Time filter (applies to vehicle-specific events only)
        if anchor_dt and ts_str:
            try:
                rec_dt = datetime.fromisoformat(ts_str)
                if rec_dt.tzinfo is None:
                    rec_dt = rec_dt.replace(tzinfo=timezone.utc)
                if abs((rec_dt - anchor_dt).total_seconds()) > _TIME_WINDOW_SECONDS:
                    # Still collect causal-chain events even outside time window
                    if vehicle_id and et in _CAUSAL_CHAIN_TYPES:
                        causal.append(rec)
                    continue
            except ValueError:
                pass

        if vehicle_id:
            if et in _CAUSAL_CHAIN_TYPES:
                causal.append(rec)
            elif _event_references_vehicle(rec, vehicle_id):
                matched.append(rec)
        else:
            matched.append(rec)

    if vehicle_id:
        # Deduplicate causal entries (they may have been added twice if no time filter)
        seen = set()
        unique_causal = []
        for r in causal:
            key = r.get("_hash", id(r))
            if key not in seen:
                seen.add(key)
                unique_causal.append(r)
        return unique_causal + matched

    return matched


def _format_record(rec: dict) -> str:
    lines = []
    ts = rec.get("ts", "")
    et = rec.get("event_type", rec.get("event", "")).upper()
    lines.append(f"[{ts}] {et}")
    payload = rec.get("payload", {})
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k == "mig":
                lines.append(f"  {k}: <MIG object>")
            elif isinstance(v, (dict, list)) and len(str(v)) > 120:
                lines.append(f"  {k}: <{type(v).__name__}>")
            else:
                lines.append(f"  {k}: {v}")
    elif payload:
        lines.append(f"  payload: {payload}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Query a mission audit log",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--mission", required=True, help="Mission ID (e.g. MSN-A1B2C3D4)")
    parser.add_argument("--vehicle", default=None, help="Vehicle ID to filter by")
    parser.add_argument(
        "--time",
        default=None,
        help=f"ISO 8601 timestamp; returns events within ±{_TIME_WINDOW_SECONDS}s",
    )
    parser.add_argument(
        "--action",
        action="store_true",
        help="Show only dispatch_command and telemetry_snapshot events (requires --vehicle)",
    )
    parser.add_argument(
        "--missions-dir",
        default=None,
        help="Directory containing mission JSONL files (default: missions/)",
    )
    args = parser.parse_args(argv)

    missions_dir = Path(args.missions_dir) if args.missions_dir else None

    try:
        results = query(
            mission_id=args.mission,
            vehicle_id=args.vehicle,
            time_str=args.time,
            show_action=args.action,
            missions_dir=missions_dir,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if not results:
        print(f"No events found for mission {args.mission}", end="")
        if args.vehicle:
            print(f" / vehicle {args.vehicle}", end="")
        if args.time:
            print(f" near {args.time}", end="")
        print()
        sys.exit(0)

    print(f"=== Audit Query: {args.mission} ===")
    if args.vehicle:
        print(f"Vehicle filter : {args.vehicle}")
    if args.time:
        print(f"Time filter    : {args.time} (±{_TIME_WINDOW_SECONDS}s)")
    print(f"Events found   : {len(results)}")
    print()

    # Filter to action events only if --action requested
    display = results
    if args.action and args.vehicle:
        action_types = {"dispatch_command", "telemetry_snapshot", "contingency_rung_executed"}
        display = [r for r in results if r.get("event_type", "") in action_types]

    for rec in display:
        print(_format_record(rec))
        print()


if __name__ == "__main__":
    main()
