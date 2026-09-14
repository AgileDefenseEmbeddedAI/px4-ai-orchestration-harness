"""
Unit tests for the contingency ladder executor (REQ-LNK-01/02).

All tests run without live SITL. Key assertions:
  (a) Executor fires rung 0 immediately on link loss.
  (b) Executor does NOT fire if link is healthy.
  (c) Executor does not call any LLM or harness API endpoint.
  (d) Audit event is written for each rung executed.
"""

from __future__ import annotations

import importlib
import inspect
import json
import sys
import time
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
import yaml

from harness.dispatch.contingency_executor import (
    ContingencyExecutor,
    _trigger_threshold,
    load_ladder,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

THREE_RUNG_LADDER = [
    {"trigger": "link_loss_T+0",  "actions": [{"cmd": "loiter", "params": {"duration_s": 30}}]},
    {"trigger": "link_loss_T+30", "actions": [{"cmd": "rtl",    "params": {}}]},
    {"trigger": "link_loss_T+60", "actions": [{"cmd": "land",   "params": {}}]},
]


@pytest.fixture
def tmp_mission_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect audit logger to a temp directory so tests don't pollute missions/."""
    import harness.audit.logger as audit_mod
    monkeypatch.setattr(audit_mod, "MISSIONS_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def executor(tmp_mission_dir: Path) -> ContingencyExecutor:
    return ContingencyExecutor(
        vehicle_id="UAV-TEST",
        mission_id="MSN-LNKTEST",
        ladder=THREE_RUNG_LADDER,
        heartbeat_timeout_s=5.0,
    )


def _advance(exc: ContingencyExecutor, seconds: float, step: float = 0.5) -> list[dict]:
    """Drive the executor forward in synthetic time, collecting all fired events.

    Ticks at t0+step, t0+2*step, ..., up to and including t0+seconds.
    The condition is checked after incrementing so the tick value never
    exceeds t0+seconds.
    """
    t0 = exc._last_heartbeat
    fired: list[dict] = []
    t = t0 + step
    while t <= t0 + seconds:
        fired.extend(exc.tick(now=t))
        t += step
    return fired


# ---------------------------------------------------------------------------
# (a) Executor fires rung 0 immediately on link loss
# ---------------------------------------------------------------------------


def test_fires_rung0_on_link_loss(executor: ContingencyExecutor) -> None:
    """Rung 0 (link_loss_T+0) fires within one tick after heartbeat times out."""
    # Synthetic time: advance beyond heartbeat_timeout_s without any heartbeat
    fired = _advance(executor, seconds=6.0)
    assert len(fired) >= 1, "Expected at least rung 0 to fire"
    first = fired[0]
    assert first["payload"]["trigger"] == "link_loss_T+0"
    assert first["payload"]["vehicle_id"] == "UAV-TEST"


def test_rung0_fires_within_timeout_plus_one_tick(executor: ContingencyExecutor) -> None:
    """Rung 0 fires at most (heartbeat_timeout_s + 1 tick) after last heartbeat."""
    t0 = executor._last_heartbeat
    # Advance just over the 5 s timeout
    fired = _advance(executor, seconds=5.5)
    assert any(e["payload"]["trigger"] == "link_loss_T+0" for e in fired)


# ---------------------------------------------------------------------------
# (b) Executor does NOT fire if link is healthy
# ---------------------------------------------------------------------------


def test_no_fire_when_link_healthy(executor: ContingencyExecutor) -> None:
    """No rungs fire when heartbeats arrive regularly."""
    t0 = executor._last_heartbeat
    t = t0
    fired: list[dict] = []
    for _ in range(10):
        t += 1.0
        executor.record_heartbeat(now=t)  # synthetic heartbeat matches synthetic tick time
        fired.extend(executor.tick(now=t))
    assert fired == [], f"Unexpected rung fires with healthy link: {fired}"


def test_no_fire_just_before_timeout(executor: ContingencyExecutor) -> None:
    """Nothing fires at 4.9 s with a 5 s timeout."""
    fired = _advance(executor, seconds=4.9)
    assert fired == []


# ---------------------------------------------------------------------------
# (c) Executor never calls any LLM or harness API endpoint
# ---------------------------------------------------------------------------


def test_no_llm_or_api_imports() -> None:
    """
    The contingency_executor module must not import any LLM or HTTP client.
    We check the module's actual import statements using ast.
    """
    import ast
    import harness.dispatch.contingency_executor as mod

    forbidden = {"openai", "anthropic", "requests", "httpx", "aiohttp", "urllib3"}
    source = inspect.getsource(mod)
    tree = ast.parse(source)

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.add(node.module.split(".")[0])

    for pkg in forbidden:
        assert pkg not in imported_modules, (
            f"contingency_executor.py must not import {pkg!r}"
        )


def test_no_outbound_http_calls(executor: ContingencyExecutor, tmp_mission_dir: Path) -> None:
    """
    Patch socket.socket to assert no network connections are opened during
    ladder execution.
    """
    import socket

    connection_attempts: list[tuple] = []

    class _NoNetSocket:
        def __init__(self, *a, **kw):
            pass
        def connect(self, addr):
            connection_attempts.append(addr)
            raise ConnectionRefusedError("test: network blocked")
        def __getattr__(self, name):
            return MagicMock()

    with patch("socket.socket", _NoNetSocket):
        # Drive the executor into link-loss and through all three rungs
        _advance(executor, seconds=70.0)

    assert connection_attempts == [], (
        f"contingency executor opened network connections: {connection_attempts}"
    )


# ---------------------------------------------------------------------------
# (d) Audit event is written for each rung executed
# ---------------------------------------------------------------------------


def test_audit_event_written_per_rung(executor: ContingencyExecutor, tmp_mission_dir: Path) -> None:
    """Each fired rung produces exactly one audit event in the mission log."""
    from harness.audit.logger import read_log

    # Drive all three rungs to completion
    _advance(executor, seconds=70.0)

    records = read_log("MSN-LNKTEST")
    rung_events = [r for r in records if r["event"] == "contingency_rung_executed"]

    assert len(rung_events) == 3, (
        f"Expected 3 rung audit events, got {len(rung_events)}: {rung_events}"
    )
    triggers = [e["payload"]["trigger"] for e in rung_events]
    assert triggers == ["link_loss_T+0", "link_loss_T+30", "link_loss_T+60"]


def test_link_loss_event_written(executor: ContingencyExecutor, tmp_mission_dir: Path) -> None:
    """A 'contingency_link_loss' event is written when link loss is first declared."""
    from harness.audit.logger import read_log

    _advance(executor, seconds=6.0)

    records = read_log("MSN-LNKTEST")
    loss_events = [r for r in records if r["event"] == "contingency_link_loss"]
    assert len(loss_events) == 1
    assert loss_events[0]["payload"]["vehicle_id"] == "UAV-TEST"


def test_audit_rung_payload_contains_actions(executor: ContingencyExecutor, tmp_mission_dir: Path) -> None:
    """Each audit rung event embeds the full action list."""
    from harness.audit.logger import read_log

    _advance(executor, seconds=70.0)
    records = read_log("MSN-LNKTEST")
    rung_events = [r for r in records if r["event"] == "contingency_rung_executed"]

    for evt in rung_events:
        assert "actions" in evt["payload"], f"Missing 'actions' in {evt}"
        assert isinstance(evt["payload"]["actions"], list)


# ---------------------------------------------------------------------------
# Ladder loading tests
# ---------------------------------------------------------------------------


def test_load_ladder_yaml(tmp_path: Path) -> None:
    ladder_yaml = tmp_path / "ladder.yaml"
    ladder_yaml.write_text(
        "rungs:\n"
        "  - trigger: 'link_loss_T+0'\n"
        "    actions:\n"
        "      - cmd: loiter\n"
        "        params: {duration_s: 30}\n"
    )
    rungs = load_ladder(ladder_yaml)
    assert len(rungs) == 1
    assert rungs[0]["trigger"] == "link_loss_T+0"


def test_load_ladder_json(tmp_path: Path) -> None:
    ladder_json = tmp_path / "ladder.json"
    ladder_json.write_text(
        json.dumps({"rungs": [{"trigger": "link_loss_T+0", "actions": []}]})
    )
    rungs = load_ladder(ladder_json)
    assert len(rungs) == 1


def test_trigger_threshold_parsing() -> None:
    assert _trigger_threshold("link_loss_T+0") == 0
    assert _trigger_threshold("link_loss_T+30") == 30
    assert _trigger_threshold("link_loss_T+60") == 60


def test_trigger_threshold_invalid() -> None:
    with pytest.raises(ValueError):
        _trigger_threshold("bad_trigger")


# ---------------------------------------------------------------------------
# Scenario file sanity check
# ---------------------------------------------------------------------------


def test_link_loss_scenario_yaml_is_valid() -> None:
    """The bundled scenario YAML parses and has the expected structure."""
    scenario_path = Path(__file__).parent / "scenarios" / "link_loss_scenario.yaml"
    assert scenario_path.exists(), f"Scenario file not found: {scenario_path}"
    data = yaml.safe_load(scenario_path.read_text())

    assert "vehicles" in data
    assert len(data["vehicles"]) == 2

    for vehicle in data["vehicles"]:
        ladder = vehicle["contingency_ladder"]["rungs"]
        assert len(ladder) == 3
        assert ladder[0]["trigger"] == "link_loss_T+0"
        assert ladder[1]["trigger"] == "link_loss_T+30"
        assert ladder[2]["trigger"] == "link_loss_T+60"

    assert data["fault_injection"]["type"] == "link_loss"
    assert data["fault_injection"]["inject_at_s"] == 15
