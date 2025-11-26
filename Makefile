.PHONY: help infra-up infra-down infra-wait backend frontend test-backend clean

help:
	@echo "Nexus Development Commands"
	@echo ""
	@echo "Infrastructure:"
	@echo "  make infra-up      Start PostgreSQL + Redis (detached)"
	@echo "  make infra-down    Stop infrastructure"
	@echo "  make infra-wait    Wait for services to be ready"
	@echo ""
	@echo "Testing:"
	@echo "  make test-backend  Start infra → run backend tests → stop infra"
	@echo ""
	@echo "Full Setup:"
	@echo "  make backend       Setup backend (install + lint + test)"
	@echo "  make frontend      Setup frontend (install + lint + test)"
	@echo ""
	@echo "See backend/Makefile and frontend/Makefile for individual targets"

infra-up:
	@echo "Starting infrastructure (PostgreSQL + Redis)..."
	docker compose -f infra/docker-compose.yml up -d db redis
	@echo "✓ Services started"

infra-wait:
	@echo "Waiting for services to be ready..."
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		if docker compose -f infra/docker-compose.yml exec -T db pg_isready -U app_user -d postgres > /dev/null 2>&1; then \
			echo "✓ PostgreSQL is ready"; \
			sleep 1; \
			break; \
		fi; \
		echo "  Waiting for PostgreSQL... (attempt $$i/10)"; \
		sleep 1; \
	done
	@docker compose -f infra/docker-compose.yml ps

infra-down:
	@echo "Stopping infrastructure..."
	docker compose -f infra/docker-compose.yml down
	@echo "✓ Services stopped"

test-backend: infra-up infra-wait
	@echo "Running backend tests..."
	cd backend && DATABASE_URL_TEST=postgresql+psycopg://app_user:password@localhost:5432/test_nexus make test
	@echo "✓ Backend tests passed"
	@$(MAKE) infra-down

backend:
	@echo "Setting up backend..."
	cd backend && make install && make lint && make test
	@echo "✓ Backend ready"

frontend:
	@echo "Setting up frontend..."
	cd frontend && make install && make lint && make test
	@echo "✓ Frontend ready"

clean:
	@echo "Cleaning up..."
	rm -rf backend/.venv backend/__pycache__ backend/.pytest_cache backend/.mypy_cache
	rm -rf frontend/node_modules frontend/dist frontend/build
	@echo "✓ Cleaned"
