# PX4 AI Orchestration Harness

[![CI](https://github.com/AgileDefenseEmbeddedAI/px4-ai-orchestration-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/AgileDefenseEmbeddedAI/px4-ai-orchestration-harness/actions/workflows/ci.yml)

AI harness that accepts natural-language mission intent, decomposes it into a validated
multi-vehicle PX4 plan (multirotor + rover), enforces hard constraints deterministically,
requires human authorization, and dispatches over ROS 2 / MAVLink 2 against SITL.

**Source PRD / Epic:** https://bytecubed.atlassian.net/wiki/spaces/EA/pages/4723179521/PRD+AI+Harness+for+Heterogeneous+Vehicle+Orchestration+PX4+Baseline+2026-09-14

**Live site:** https://AgileDefenseEmbeddedAI.github.io/px4-ai-orchestration-harness/

> This is an auto-generated prototype. A primary build workflow builds the foundation
> directly on the default branch; follow-on tickets live as GitHub issues and
> [Claude Code](https://github.com/anthropics/claude-code-action) implements each one
> as a pull request. Pull requests are merged by a human.

---

## Overview

```
natural-language intent
        |
        v
  [LLM Planner]  — config/model.yaml controls provider, endpoint, model
        |
        v
  Mission Intent Graph (MIG)  — schemas/mig.json
        |
        v
  [Deterministic Validator]  — geofence, altitude, RTL, deconfliction
        |
     pass / fail
        |
        v (pass only)
  [Human Authorization]  — POST /authorize/{id}  (operator name required)
        |
        v
  [Dispatch]
    ├── ROS 2 uXRCE-DDS bridge  (multirotor + rover)
    └── MAVLink 2 / pymavlink   (secondary transport)
        |
        v
  [Audit Log]  — missions/<id>.jsonl  (written before dispatch)
```

The LLM **never** writes directly to a vehicle. The validator **never** calls the LLM.
Audit records are written **before** dispatch — dispatch failure cannot corrupt the trail.

---

## Running

### Without SITL (API + stub planner)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure LLM provider (or skip for stub mode)
cp config/model.yaml.example config/model.yaml
# Edit config/model.yaml — set provider, base_url, model, api_key_env

# 3. Start the harness
uvicorn harness.api.main:app --reload --host 0.0.0.0 --port 8000

# 4. Submit a mission intent
curl -X POST http://localhost:8000/intent \
  -H "Content-Type: application/json" \
  -d '{"text": "Scout Alpha-7 with UAV at 60m, rover secures the perimeter"}'

# 5. Poll for the plan
curl http://localhost:8000/plan/<mission_id>

# 6. Authorize and dispatch
curl -X POST http://localhost:8000/authorize/<mission_id> \
  -H "Content-Type: application/json" \
  -d '{"authorized": true, "operator": "Capt. Reynolds"}'
```

Or use `make dev` to run with a single command.

### With SITL

```bash
# Requires PX4-Autopilot cloned at $PX4_DIR (default: ~/PX4-Autopilot)
# and Gazebo Garden installed

# Build SITL targets first (one-time)
cd $PX4_DIR
make px4_sitl_default

# Launch both SITL instances
./scripts/launch_sitl.sh

# Then start the harness in another terminal
make dev
```

### Make targets

| Target                  | Description                                                  |
|-------------------------|--------------------------------------------------------------|
| `make dev`              | Start FastAPI harness with auto-reload                       |
| `make test`             | Run full pytest suite (verbose)                              |
| `make test-ci`          | Run pytest with fail-fast (used in CI)                       |
| `make install`          | Install runtime Python dependencies                          |
| `make lint`             | Syntax-check core Python modules                             |
| `make license-scan`     | Fail build on any GPL/LGPL/AGPL dependency (pip-licenses)    |
| `make validate-corpus`  | Assert corpus has >=8 entries; all must be rejected          |
| `make schema-lint`      | Validate all schemas/ as valid JSON Schema Draft-07          |
| `make e2e-ros2`         | Run ROS 2 transport mock tests                               |
| `make e2e-mavlink`      | Run MAVLink 2 transport mock tests                           |

---

## Configuration

### `config/model.yaml`

Controls the LLM provider. Copy `config/model.yaml.example` to get started.

```yaml
provider: openai
base_url: null          # null = OpenAI default; http://localhost:11434/v1 for Ollama
model: gpt-4o-mini
api_key_env: OPENAI_API_KEY
```

Without a `config/model.yaml` or without a reachable LLM endpoint, the planner
falls back to a deterministic stub plan for development and testing.

### `config/vehicles.yaml`

Fleet definition: vehicle types, SITL targets, MAVLink sysids, ROS 2 namespaces.

### `config/constraints.yaml`

Geofence polygon, airspace volumes, altitude limits, RTL requirement.
The validator reads these on startup. Edit to match your operational area.

---

## API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/intent` | Submit natural-language mission intent |
| `GET` | `/plan/{id}` | Get current mission state + MIG |
| `POST` | `/authorize/{id}` | Human authorization gate |
| `GET` | `/missions` | List all missions |
| `GET` | `/audit/{id}` | Read the JSONL audit trail |
| `GET` | `/docs` | Interactive API docs (Swagger UI) |

---

## Repo Layout

```
harness/
  api/          — FastAPI app, Pydantic models, REST routes
  planner/      — MIG builder + LLM intent decomposer
  validator/    — Deterministic constraint checker (no LLM)
  dispatch/     — ROS 2 + MAVLink 2 transport stubs
  audit/        — Immutable JSONL audit logger
  ui/           — Jinja2 templates for human-authorization screen

config/
  model.yaml.example   — LLM provider config template
  constraints.yaml     — Geofence, altitude limits, hard rules
  vehicles.yaml        — Fleet definition

schemas/
  mig.json      — Mission Intent Graph JSON Schema v1.0
  val.json      — Vehicle Action List JSON Schema v1.0

tests/
  scenarios/    — Named YAML scenario fixtures
  adversarial/  — Plans that MUST be rejected by the validator

scripts/
  launch_sitl.sh      — Launch multirotor + rover SITL instances
  replay_mission.py   — Replay a recorded mission from audit log

public/
  index.html    — GitHub Pages static frontend (live demo + docs)
```

---

## Constraints

The validator enforces these deterministically — no LLM is involved:

1. **Geofence** — All waypoints inside the configured polygon (Shapely 2.x)
2. **Altitude bounds** — Multirotors between `min_alt_m` and `max_alt_m` AGL
3. **RTL requirement** — Every vehicle must have a waypoint with `role: rtl`
4. **Waypoint integrity** — No dangling waypoint references
5. **Vehicle assignment** — At least one vehicle assigned
6. **Human authorization** — No dispatch without recorded operator authorization

---

## Planned Follow-On Work

These will be implemented as GitHub issues after the primary build:

1. MIG schema and LLM-backed intent-to-plan decomposer (full implementation)
2. Deterministic plan validator with geofence, deconfliction, and hard-constraint enforcement
3. Human authorization screen and authorization-gated dispatch flow
4. ROS 2 VAL transport and SITL integration for multirotor + rover dispatch
5. MAVLink 2 secondary VAL transport and dual-transport scenario parity test
6. Link-loss contingency ladder autonomous execution and fault injection tests
7. Immutable audit log, mission replay tool, and queryable why-did-X-do-Y interface
8. CI pipeline: license scan, adversarial corpus gate, dual-transport parity, scenario suite

---

## License

BSD-3-Clause. All dependencies are BSD-3-Clause compatible (`pip-licenses` enforced in CI).
