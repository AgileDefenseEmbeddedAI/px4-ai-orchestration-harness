.PHONY: dev test test-ci install lint license-scan validate-corpus schema-lint \
        e2e-ros2 e2e-mavlink check-config help

help:
	@echo "PX4 AI Orchestration Harness — available targets:"
	@echo "  install          Install runtime Python dependencies"
	@echo "  dev              Start FastAPI development server (port 8000)"
	@echo "  test             Run full pytest suite"
	@echo "  test-ci          Run pytest with fail-fast and short tracebacks (used in CI)"
	@echo "  lint             Syntax-check core Python modules"
	@echo "  license-scan     Fail build on any GPL/LGPL/AGPL dependency"
	@echo "  validate-corpus  Assert corpus has >=8 entries; all must be rejected"
	@echo "  schema-lint      Validate all schemas/ are valid JSON Schema Draft-07"
	@echo "  e2e-ros2         Run ROS 2 transport mock tests"
	@echo "  e2e-mavlink      Run MAVLink 2 transport mock tests"

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

test-ci:
	pytest tests/ -x --tb=short

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

license-scan:
	pip-licenses --format=markdown --fail-on="GPL;LGPL;AGPL"

validate-corpus:
	@CORPUS_COUNT=$$(ls tests/adversarial/*.yaml 2>/dev/null | wc -l | tr -d ' '); \
	echo "[validate-corpus] Found $$CORPUS_COUNT adversarial entries"; \
	if [ "$$CORPUS_COUNT" -lt 8 ]; then \
		echo "[validate-corpus] FAIL: need >= 8 adversarial entries, found $$CORPUS_COUNT"; \
		exit 1; \
	fi; \
	echo "[validate-corpus] Count check PASS ($$CORPUS_COUNT >= 8)"
	pytest tests/test_adversarial_corpus.py -v --tb=short

schema-lint:
	pytest tests/test_schema_lint.py -v --tb=short

e2e-ros2:
	pytest tests/test_transport_parity.py -v -k "ros2" --tb=short

e2e-mavlink:
	pytest tests/test_transport_parity.py -v -k "mavlink" --tb=short
