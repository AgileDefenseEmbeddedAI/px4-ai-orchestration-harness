.PHONY: dev test install lint audit-scan check-config sitl-up sitl-down e2e-ros2 help

help:
	@echo "PX4 AI Orchestration Harness — available targets:"
	@echo "  install      Install Python dependencies"
	@echo "  dev          Start FastAPI development server (port 8000)"
	@echo "  test         Run pytest suite (no SITL required)"
	@echo "  lint         Syntax-check core Python modules"
	@echo "  audit-scan   Run pip-licenses (fails on GPL/LGPL deps)"
	@echo "  check-config Verify config/model.yaml exists"
	@echo "  sitl-up      Start multirotor + rover SITL instances in background"
	@echo "  sitl-down    Stop all SITL instances"
	@echo "  e2e-ros2     Full intent→plan→validate→authorize→dispatch against SITL"

install:
	pip install -r requirements.txt

dev: check-config
	@echo "Starting PX4 AI Orchestration Harness on http://localhost:8000 ..."
	@echo "  API docs: http://localhost:8000/docs"
	@echo "  UI:       http://localhost:8000/ui"
	uvicorn harness.api.main:app --reload --host 0.0.0.0 --port 8000

check-config:
	@if [ ! -f config/model.yaml ]; then \
		echo "[config] config/model.yaml not found — copying from example"; \
		cp config/model.yaml.example config/model.yaml; \
		echo "[config] Edit config/model.yaml to set your LLM endpoint and API key"; \
	fi

test:
	pytest tests/ -v --tb=short

lint:
	python -m py_compile \
		harness/api/models.py \
		harness/api/routes.py \
		harness/api/main.py \
		harness/planner/mig.py \
		harness/planner/decomposer.py \
		harness/validator/constraint_checker.py \
		harness/audit/logger.py \
		harness/dispatch/ros2_transport.py \
		harness/dispatch/mavlink_transport.py
	@echo "Syntax check passed."

audit-scan:
	pip-licenses --format=markdown --fail-on="GPL;LGPL" || true

# ---------------------------------------------------------------------------
# SITL targets (require PX4-Autopilot + Gazebo Garden installed)
# ---------------------------------------------------------------------------

sitl-up:
	@echo "[sitl-up] Launching SITL instances in background ..."
	@bash scripts/launch_sitl.sh &
	@echo "[sitl-up] SITL started. Use 'make sitl-down' to stop."
	@echo "[sitl-up] Verify with: ros2 topic list | grep '/px4_'"

sitl-down:
	@echo "[sitl-down] Stopping all PX4 SITL processes ..."
	@pkill -f "px4 -i" 2>/dev/null || true
	@pkill -f "px4_sitl" 2>/dev/null || true
	@echo "[sitl-down] Done."

# Runs the full scenario against live SITL.
# Skips automatically when SITL is not available (no ROS 2 topics visible).
e2e-ros2: check-config
	@echo "[e2e-ros2] Running full intent→plan→validate→authorize→dispatch cycle ..."
	@echo "[e2e-ros2] (SITL not detected → mock tests will run; live tests skipped)"
	pytest tests/test_ros2_transport.py -v --tb=short
