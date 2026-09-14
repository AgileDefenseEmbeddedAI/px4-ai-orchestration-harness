#!/usr/bin/env python3
"""
Replay a recorded mission from its JSONL audit log.

Usage:
    python scripts/replay_mission.py <mission_id>
    python scripts/replay_mission.py <mission_id> --missions-dir /path/to/missions
"""

import argparse
import sys
from pathlib import Path

# Allow running from the repo root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.audit.replay import replay


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Replay a mission from its JSONL audit log",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("mission_id", help="Mission ID (e.g. MSN-A1B2C3D4)")
    parser.add_argument(
        "--missions-dir",
        default=None,
        help="Directory containing mission JSONL files (default: missions/)",
    )
    args = parser.parse_args()

    missions_dir = Path(args.missions_dir) if args.missions_dir else None
    result = replay(args.mission_id, missions_dir=missions_dir, verbose=True)

    if not result["chain_valid"]:
        print("\nWARNING: Hash chain violations detected:")
        for err in result["chain_errors"]:
            print(f"  {err}")
        sys.exit(2)

    if result["verdict_match"] is False:
        print("\nWARNING: Replayed verdict does not match stored verdict.")
        sys.exit(3)

    sys.exit(0)
