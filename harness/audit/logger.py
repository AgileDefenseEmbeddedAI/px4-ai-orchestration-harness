"""
Immutable JSONL audit logger.

Each mission gets its own append-only .jsonl file under missions/.
Records are written before dispatch; a dispatch failure cannot corrupt the trail.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MISSIONS_DIR = Path("missions")
logger = logging.getLogger(__name__)


def _mission_file(mission_id: str) -> Path:
    MISSIONS_DIR.mkdir(exist_ok=True)
    return MISSIONS_DIR / f"{mission_id}.jsonl"


def log_event(mission_id: str, event_type: str, payload: Any) -> None:
    """Append an immutable audit record to the mission's JSONL file."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mission_id": mission_id,
        "event": event_type,
        "payload": payload,
    }
    try:
        with _mission_file(mission_id).open("a") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
    except OSError as exc:
        logger.error(f"[audit] Failed to write audit record for {mission_id}: {exc}")


def read_log(mission_id: str) -> list[dict]:
    """Read all audit records for a mission, in insertion order."""
    path = _mission_file(mission_id)
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning(f"[audit] Corrupt record in {path}: {line!r}")
    return records
