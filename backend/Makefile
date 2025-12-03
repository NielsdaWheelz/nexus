.PHONY: help install dev dev-worker test test-unit test-integration test-all lint format type-check clean check-uow migrate migration

help:
	@echo "Backend Makefile"
	@echo ""
	@echo "  make install          Install dependencies with uv"
	@echo "  make dev              Start development server (uvicorn with reload)"
	@echo "  make dev-worker       Start Celery worker (documents + embeddings queues)"
	@echo "  make test             Run unit tests (alias for test-unit)"
	@echo "  make test-unit        Run unit tests (eager Celery mode)"
	@echo "  make test-integration Run integration tests (real Celery/Redis)"
	@echo "  make test-all         Run all tests (unit + integration)"
	@echo "  make lint             Run linters (ruff check + black check + mypy)"
	@echo "  make format           Auto-format code (black + ruff fix)"
	@echo "  make type-check       Run type checker (mypy)"
	@echo "  make check-uow        Check Unit of Work pattern (no illegal commits)"
	@echo "  make migrate          Run database migrations (alembic upgrade head)"
	@echo "  make migration        Generate new migration (alembic revision --autogenerate)"
	@echo "  make clean            Remove venv and cache"

VENV := .venv
PYTHON := $(VENV)/bin/python
UV := uv

install:
	@echo "Installing dependencies..."
	$(UV) sync --all-extras
	@echo "✓ Dependencies installed"

dev: install
	@echo "Starting development server..."
	$(PYTHON) -m uvicorn app.main:app --reload

dev-worker: install
	@echo "Starting Celery worker..."
	$(PYTHON) -m celery -A app.celery_app worker -Q documents,embeddings -l info

test-unit: install
	@echo "Running unit tests..."
	$(PYTHON) -m pytest -m "not integration" --cov=app --cov-report=term
	@echo "✓ Unit tests passed"

test-integration: install
	@echo "Running integration tests..."
	$(PYTHON) -m pytest tests/integration -m integration -v
	@echo "✓ Integration tests passed"

test-all: install
	@echo "Running all tests..."
	$(PYTHON) -m pytest --cov=app --cov-report=term
	@echo "✓ All tests passed"

test: test-unit

check-uow:
	@echo "Checking Unit of Work pattern..."
	@bash scripts/check_uow_violations.sh

lint: install check-uow
	@echo "Running ruff check..."
	$(PYTHON) -m ruff check . --line-length=100
	@echo "Running black check..."
	$(PYTHON) -m black --check . --line-length=100
	@echo "Running mypy..."
	$(PYTHON) -m mypy app tests || true
	@echo "✓ Linting complete"

format: install
	@echo "Running black..."
	$(PYTHON) -m black . --line-length=100
	@echo "Running ruff fix..."
	$(PYTHON) -m ruff check . --fix --line-length=100
	@echo "✓ Formatting complete"

type-check: install
	@echo "Running mypy..."
	$(PYTHON) -m mypy app tests
	@echo "✓ Type checking passed"

migrate:
	@echo "Running database migrations..."
	$(PYTHON) -m alembic upgrade head
	@echo "✓ Migrations applied"

migration:
	@echo "Generating new migration (autogenerate)..."
	@read -p "Migration message: " msg; \
	$(PYTHON) -m alembic revision --autogenerate -m "$$msg"
	@echo "✓ Migration generated. Review the file before committing!"

clean:
	@echo "Cleaning up..."
	rm -rf $(VENV) __pycache__ .pytest_cache .mypy_cache .ruff_cache *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Cleaned"
