"""
Immutable JSONL audit logger with SHA-256 hash chain.

Each mission gets its own append-only .jsonl file under missions/.
Records are written before dispatch; a dispatch failure cannot corrupt the trail.
Each line carries a _hash field (SHA-256 of the record content + previous hash)
that forms a tamper-evident chain.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MISSIONS_DIR = Path("missions")
VALIDATOR_VERSION = "1.0"

logger = logging.getLogger(__name__)


def _resolve_dir(missions_dir: Path | None) -> Path:
    d = missions_dir or MISSIONS_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _mission_file(mission_id: str, missions_dir: Path | None = None) -> Path:
    return _resolve_dir(missions_dir) / f"{mission_id}.jsonl"


def _compute_hash(record_without_hash: dict, prev_hash: str = "") -> str:
    content = json.dumps(record_without_hash, sort_keys=True, default=str) + prev_hash
    return hashlib.sha256(content.encode()).hexdigest()


def _last_hash(mission_id: str, missions_dir: Path | None = None) -> str:
    path = _mission_file(mission_id, missions_dir)
    if not path.exists():
        return ""
    last = ""
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rec = json.loads(line)
                    last = rec.get("_hash", "")
                except json.JSONDecodeError:
                    pass
    return last


def log_event(
    mission_id: str,
    event_type: str,
    payload: Any,
    missions_dir: Path | None = None,
) -> None:
    """Append a hash-chained audit record to the mission's JSONL file."""
    prev_hash = _last_hash(mission_id, missions_dir)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mission_id": mission_id,
        "event_type": event_type,
        "payload": payload,
    }
    record["_hash"] = _compute_hash(record, prev_hash)
    try:
        with _mission_file(mission_id, missions_dir).open("a") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
    except OSError as exc:
        logger.error(f"[audit] Failed to write audit record for {mission_id}: {exc}")


def read_log(mission_id: str, missions_dir: Path | None = None) -> list[dict]:
    """Read all audit records for a mission, in insertion order."""
    path = _mission_file(mission_id, missions_dir)
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


def verify_chain(mission_id: str, missions_dir: Path | None = None) -> tuple[bool, list[str]]:
    """
    Verify the SHA-256 hash chain of a mission log.

    Returns (is_valid, error_messages). Any in-place mutation of a log line
    or deletion/insertion of lines will produce a non-empty error list.
    """
    path = _mission_file(mission_id, missions_dir)
    if not path.exists():
        return True, []

    errors: list[str] = []
    prev_hash = ""

    with path.open() as fh:
        for i, raw_line in enumerate(fh, 1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                errors.append(f"Line {i}: JSON decode error")
                continue

            stored_hash = record.get("_hash", "")
            record_without_hash = {k: v for k, v in record.items() if k != "_hash"}
            expected_hash = _compute_hash(record_without_hash, prev_hash)

            if stored_hash != expected_hash:
                errors.append(
                    f"Line {i}: hash mismatch "
                    f"(stored={stored_hash[:12]}…, expected={expected_hash[:12]}…)"
                )

            prev_hash = stored_hash

    return len(errors) == 0, errors
