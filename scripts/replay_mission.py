#!/usr/bin/env python3
"""
Replay a recorded mission from its JSONL audit log.

Usage:
    python scripts/replay_mission.py MSN-A1B2C3D4
    python scripts/replay_mission.py MSN-A1B2C3D4 --missions-dir /path/to/missions
"""

import argparse
import json
import sys
from pathlib import Path


def replay(mission_id: str, missions_dir: Path = Path("missions")) -> None:
    log_file = missions_dir / f"{mission_id}.jsonl"
    if not log_file.exists():
        print(f"ERROR: No audit log found for mission {mission_id}", file=sys.stderr)
        print(f"       Looked in: {log_file.resolve()}", file=sys.stderr)
        sys.exit(1)

    records = []
    with log_file.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    print(f"WARNING: Skipping corrupt record: {exc}", file=sys.stderr)

    print(f"=== Mission Replay: {mission_id} ===")
    print(f"Log file : {log_file.resolve()}")
    print(f"Events   : {len(records)}")
    print()

    for i, rec in enumerate(records, 1):
        print(f"[{i:02d}] {rec.get('ts', 'unknown')}  EVENT: {rec.get('event', '').upper()}")
        payload = rec.get("payload", {})
        if isinstance(payload, dict):
            for key, val in payload.items():
                if key in ("mig", "val"):
                    # Summarize large nested objects
                    print(f"       {key}: <{type(val).__name__}>")
                else:
                    print(f"       {key}: {val}")
        elif payload:
            print(f"       payload: {payload}")
        print()

    # Summary line
    statuses = [r.get("event") for r in records]
    if "dispatch_complete" in statuses:
        print("Outcome: DISPATCHED")
    elif "authorization_rejected" in statuses:
        print("Outcome: REJECTED")
    elif "validation_failed" in statuses:
        print("Outcome: VALIDATION FAILED")
    elif "planning_error" in statuses:
        print("Outcome: PLANNING ERROR")
    else:
        print(f"Outcome: INCOMPLETE (last event: {statuses[-1] if statuses else 'none'})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Replay a mission from its JSONL audit log",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("mission_id", help="Mission ID (e.g. MSN-A1B2C3D4)")
    parser.add_argument(
        "--missions-dir",
        default="missions",
        help="Directory containing mission JSONL files (default: missions/)",
    )
    args = parser.parse_args()
    replay(args.mission_id, Path(args.missions_dir))
