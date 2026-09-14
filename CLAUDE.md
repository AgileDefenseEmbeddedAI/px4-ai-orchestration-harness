# Prototype guide for Claude Code

AI harness that accepts natural-language mission intent, decomposes it into a validated multi-vehicle PX4 plan (multirotor + rover), enforces hard constraints deterministically, requires human authorization, and dispatches over ROS 2 / MAVLink 2 against SITL.

The source PRD / Epic: https://bytecubed.atlassian.net/wiki/spaces/EA/pages/4723179521/PRD+AI+Harness+for+Heterogeneous+Vehicle+Orchestration+PX4+Baseline+2026-09-14

## How this repo is built

This prototype is built in two phases:

1. **Primary build** — `.github/workflows/build.yml` runs you (Claude Code) once to
   build as much of the product as possible, committed directly to the default branch.
2. **Follow-on issues** — after the primary build, each item below is filed as a GitHub
   issue. `.github/workflows/claude.yml` then runs you to implement that one issue as an
   incremental change on top of the default branch and open a pull request. Those pull
   requests are reviewed and merged by a human — do not merge them yourself.

## Live deployment (GitHub Pages)

`.github/workflows/pages.yml` deploys this repo to GitHub Pages on every push to the
default branch, publishing to https://AgileDefenseEmbeddedAI.github.io/px4-ai-orchestration-harness/. The deploy auto-detects what to serve: it
builds a Node project that has a `build` script and publishes its output (`dist`/`build`/
`out`/`public`), otherwise it serves a static directory containing `index.html`, and
otherwise falls back to a landing page generated from the README. **To make the live site
useful, give the prototype a web-servable front end**: a `build` script that emits static
files into one of those directories, or a static `index.html` at the repo root or in
`public/`. A pure backend with no static entry point still deploys (the README fallback),
it just won't show the product.

## Planned follow-on work

These will be filed as issues after the primary build, so you don't need to complete
them during the primary build — just leave a clean foundation they can build on:

1. Implement MIG schema and LLM-backed intent-to-plan decomposer
2. Build deterministic plan validator with geofence, deconfliction, and hard-constraint enforcement
3. Implement human authorization screen and authorization-gated dispatch flow
4. Implement ROS 2 VAL transport and SITL integration for multirotor + rover dispatch
5. Implement MAVLink 2 secondary VAL transport and dual-transport scenario parity test
6. Implement link-loss contingency ladder autonomous execution and fault injection tests
7. Implement immutable audit log, mission replay tool, and queryable why-did-X-do-Y interface
8. Add CI pipeline: license scan, adversarial corpus gate, dual-transport parity, and scenario suite

## Design system

This repo ships the **Agile Defense design system** as a Claude Code skill at
`.claude/skills/agile-defense-design/`. Use it for **all** UI you build so the prototype
looks on-brand from the first build, not generic:

- Read `.claude/skills/agile-defense-design/SKILL.md` and `README.md` first — they carry
  the brand context, voice, and visual foundations.
- Import `.claude/skills/agile-defense-design/colors_and_type.css` before your own styles
  to inherit the color/type/spacing tokens and `.t-*` semantic type classes.
- Reuse the authored patterns in `reference/component-library.html` and the `ui_kits/`
  (marketing + Agile Labs) rather than inventing new components.
- Pull logos, capability icons, and photography from the skill's `assets/`.

**Hard brand rules:** deep navy (`#061033`) or white canvases with navy (`#0b2451`) cards;
a single red accent (`#d23c3a`); Helvetica Neue (fall through Helvetica → Arial); **sharp
corners — no rounded cards**; no shadows (rely on contrast); no emoji; no exclamation points.

## Tech stack & conventions

## Stack & Conventions

### Runtime
- **Language:** Python 3.11+
- **ROS 2 distribution:** Humble (primary data path via px4_msgs + px4_ros_com uXRCE-DDS bridge)
- **Simulation:** PX4 SITL (v1.14+) launched via `make px4_sitl gz_x500` (multirotor) and `make px4_sitl gz_rover_ackermann` (rover); Gazebo Garden
- **MAVLink 2 path:** pymavlink 2.x (BSD-3-Clause) as secondary VAL transport
- **AI / LLM client:** `openai` SDK wired to a configurable base URL; local/air-gapped inference via Ollama-compatible endpoint — all config-file-driven (`config/model.yaml`), zero code changes to switch providers
- **Validation engine:** Pure-Python deterministic rule checker (no ML); shapely 2.x for geofence geometry
- **Audit log:** Append-only JSONL files, one per mission, stored under `missions/`
- **HTTP API:** FastAPI + uvicorn (BSD-3-Clause)
- **Authorization UI:** Minimal web UI served by FastAPI (Jinja2 templates + vanilla JS); no heavyweight frontend framework
- **Testing:** pytest + pytest-asyncio; CI runs the full scenario suite + adversarial corpus on every push

### Repo layout
```
harness/
  api/          # FastAPI app — intent ingestion + auth endpoints
  planner/      # MIG builder + plan decomposer (calls LLM)
  validator/    # Deterministic constraint checker
  dispatch/     # VAL: ROS 2 transport + MAVLink 2 transport
  audit/        # Immutable JSONL audit logger + replay tool
  ui/           # Jinja2 templates for human-authorization screen
config/
  model.yaml    # LLM provider, endpoint, model name
  constraints.yaml  # Geofence polygons, airspace volumes, hard limits
  vehicles.yaml # Fleet definition (class, SITL target, MAVLink sysid)
tests/
  scenarios/    # Named YAML scenario fixtures
  adversarial/  # Adversarial corpus (YAML plans that MUST be rejected)
scripts/
  launch_sitl.sh   # Spins up multirotor + rover SITL instances
  replay_mission.py
```

### Key conventions
- BSD-3-Clause only; `pip-licenses` license scan runs in CI and fails on any GPL dependency
- `config/model.yaml` controls `provider`, `base_url`, `model`, `api_key_env`; no hardcoded provider strings outside this file
- MIG and VAL interfaces are versioned JSON schemas under `schemas/`; breaking changes bump schema `version` field
- The validator NEVER calls the LLM; the LLM NEVER writes directly to a vehicle
- All audit records are written before dispatch; dispatch failure does not corrupt the audit trail
- `make dev` brings up FastAPI + two SITL instances locally; `make test` runs pytest suite

### How to run (no SITL)
```bash
pip install -r requirements.txt
cp config/model.yaml.example config/model.yaml   # fill in endpoint
uvicorn harness.api.main:app --reload
# POST /intent  ->  GET /plan/{id}  ->  POST /authorize/{id}  ->  dispatch
```


## Working agreement

- Build the simplest thing that satisfies the goal — this is a prototype, not
  production. Favor a working end-to-end slice over breadth.
- Keep the project runnable at every step. Document any new setup/run command in the
  README under a "Running" section.
- For follow-on issues, open one pull request per issue and reference the issue with
  "Closes #<number>". Never merge your own pull request.
- Don't introduce secrets or external services that require credentials the repo
  doesn't have.
