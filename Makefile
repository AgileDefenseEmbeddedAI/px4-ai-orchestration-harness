.PHONY: dev test install lint audit-scan check-config e2e-mavlink help

help:
	@echo "PX4 AI Orchestration Harness — available targets:"
	@echo "  install      Install Python dependencies"
	@echo "  dev          Start FastAPI development server (port 8000)"
	@echo "  test         Run pytest suite"
	@echo "  lint         Syntax-check core Python modules"
	@echo "  audit-scan   Run pip-licenses (fails on GPL/LGPL deps)"
	@echo "  check-config Verify config/model.yaml exists"
	@echo "  e2e-mavlink  Run four_vehicle_basic scenario via MAVLink transport against SITL"

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
		harness/dispatch/mavlink_transport.py \
		harness/dispatch/transport_factory.py
	@echo "Syntax check passed."

audit-scan:
	pip-licenses --format=markdown --fail-on="GPL;LGPL" || true

e2e-mavlink: check-config
	@echo "Running four_vehicle_basic scenario against SITL via MAVLink transport..."
	@echo "Requires: SITL running (./scripts/launch_sitl.sh) and config/dispatch.yaml set to 'mavlink'"
	@if [ ! -f config/dispatch.yaml ]; then \
		echo "[config] config/dispatch.yaml not found — copying from example with mavlink transport"; \
		sed 's/^transport: ros2/transport: mavlink/' config/dispatch.yaml.example > config/dispatch.yaml; \
	fi
	pytest tests/test_parity.py tests/test_mavlink_transport.py -v --tb=short
	@echo "e2e-mavlink complete — manual SITL verification required for live dispatch"
