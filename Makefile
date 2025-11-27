.PHONY: help infra infra-up infra-down infra-wait backend-dev frontend-dev backend-test backend-lint backend-format backend-full frontend-test frontend-lint frontend-format frontend-full clean

help:
	@echo "Nexus Development Commands"
	@echo ""
	@echo "Infrastructure:"
	@echo "  make infra         Start PostgreSQL + Redis (foreground with logs, Ctrl+C to stop)"
	@echo "  make infra-up      Start PostgreSQL + Redis (background, detached)"
	@echo "  make infra-down    Stop infrastructure"
	@echo ""
	@echo "Development Servers (from root, includes infra setup):"
	@echo "  make backend-dev   Start backend dev server (FastAPI on :8000, auto-starts infra)"
	@echo "  make frontend-dev  Start frontend dev server (Next.js on :3000)"
	@echo ""
	@echo "Backend Quality Checks:"
	@echo "  make backend-test   Run backend tests (isolated test DB, auto cleanup)"
	@echo "  make backend-lint   Run linters (ruff, black, mypy - check only)"
	@echo "  make backend-format Auto-format code (black, ruff)"
	@echo "  make backend-full   Full setup & checks (install + lint + format + test + type-check)"
	@echo ""
	@echo "Frontend Quality Checks:"
	@echo "  make frontend-test   Run frontend tests"
	@echo "  make frontend-lint   Run linter (eslint - check only)"
	@echo "  make frontend-format Auto-format code (prettier)"
	@echo "  make frontend-full   Full setup & checks (install + lint + format + test)"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean         Remove venv, node_modules, build artifacts"
	@echo ""
	@echo "Note: For individual targets, see backend/Makefile or frontend/Makefile"

# ============================================================================
# Infrastructure Orchestration
# ============================================================================

infra:
	@echo "Starting infrastructure (PostgreSQL + Redis) in foreground..."
	@echo "Press Ctrl+C to stop"
	docker compose -f infra/docker-compose.yml up db redis

infra-up:
	@echo "Starting infrastructure (PostgreSQL + Redis) in background..."
	docker compose -f infra/docker-compose.yml up -d db redis
	@echo "✓ Services started"
	@docker compose -f infra/docker-compose.yml ps

infra-down:
	@echo "Stopping infrastructure..."
	docker compose -f infra/docker-compose.yml down
	@echo "✓ Services stopped"

infra-wait:
	@echo "Waiting for PostgreSQL to be ready..."
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		if docker compose -f infra/docker-compose.yml exec -T db pg_isready -U app_user -d postgres > /dev/null 2>&1; then \
			echo "✓ PostgreSQL is ready"; \
			sleep 1; \
			break; \
		fi; \
		echo "  Waiting... (attempt $$i/10)"; \
		sleep 1; \
	done

# ============================================================================
# Development Servers (with infrastructure)
# ============================================================================

backend-dev: infra-up infra-wait
	cd backend && make dev

frontend-dev:
	cd frontend && make dev

# ============================================================================
# Backend Targets
# ============================================================================

backend-test:
	@echo "Starting isolated test database..."
	docker compose -f infra/docker-compose.yml --profile test up -d test-db
	@echo "Waiting for test database to be ready..."
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		if docker compose -f infra/docker-compose.yml --profile test exec -T test-db pg_isready -U app_user -d test_nexus > /dev/null 2>&1; then \
			echo "✓ Test database is ready"; \
			break; \
		fi; \
		echo "  Waiting... (attempt $$i/10)"; \
		sleep 1; \
	done
	@echo "Running database migrations..."
	cd backend && DATABASE_URL=postgresql+psycopg://app_user:password@localhost:5433/test_nexus .venv/bin/alembic upgrade head
	@echo "Running backend tests..."
	cd backend && DATABASE_URL_TEST=postgresql+psycopg://app_user:password@localhost:5433/test_nexus make test
	@echo "Stopping test database..."
	docker compose -f infra/docker-compose.yml --profile test down test-db
	@echo "✓ Test database cleaned up"

backend-lint:
	cd backend && make lint

backend-format:
	cd backend && make format

backend-full: backend-lint backend-format backend-test
	cd backend && make install && make type-check
	@echo "✓ Backend full checks passed"

# ============================================================================
# Frontend Targets
# ============================================================================

frontend-test:
	cd frontend && make test

frontend-lint:
	cd frontend && make lint

frontend-format:
	cd frontend && make format

frontend-full: frontend-lint frontend-format frontend-test
	cd frontend && make install
	@echo "✓ Frontend full checks passed"

# ============================================================================
# Cleanup
# ============================================================================

clean:
	@echo "Cleaning up backend and frontend..."
	cd backend && make clean
	cd frontend && make clean
	@echo "✓ Cleaned"
