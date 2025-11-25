.PHONY: help install test lint format type-check clean

help:
	@echo "Backend Makefile"
	@echo ""
	@echo "  make install      Install dependencies with uv"
	@echo "  make test         Run tests (pytest)"
	@echo "  make lint         Run linters (ruff check + black check + mypy)"
	@echo "  make format       Auto-format code (black + ruff fix)"
	@echo "  make type-check   Run type checker (mypy)"
	@echo "  make clean        Remove venv and cache"

VENV := .venv
PYTHON := $(VENV)/bin/python
UV := uv

install:
	@echo "Creating virtual environment..."
	$(UV) venv
	@echo "Installing dependencies..."
	$(UV) pip install -e ".[dev]"
	@echo "✓ Dependencies installed"

test: install
	@echo "Running tests..."
	$(PYTHON) -m pytest --cov=app --cov-report=term
	@echo "✓ Tests passed"

lint: install
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

clean:
	@echo "Cleaning up..."
	rm -rf $(VENV) __pycache__ .pytest_cache .mypy_cache .ruff_cache *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Cleaned"
