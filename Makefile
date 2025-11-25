.PHONY: help infra-up infra-down backend frontend clean

help:
	@echo "Nexus Development Commands"
	@echo ""
	@echo "Infrastructure:"
	@echo "  make infra-up      Start PostgreSQL + Redis"
	@echo "  make infra-down    Stop infrastructure"
	@echo ""
	@echo "Full Setup:"
	@echo "  make backend       Setup backend (install + lint + test)"
	@echo "  make frontend      Setup frontend (install + lint + test)"
	@echo ""
	@echo "See backend/Makefile and frontend/Makefile for individual targets"

infra-up:
	@echo "Starting infrastructure (PostgreSQL + Redis)..."
	docker compose -f infra/docker-compose.yml up -d db redis
	@echo "✓ Services started. Waiting for health checks..."
	@sleep 5
	@docker compose -f infra/docker-compose.yml ps

infra-down:
	@echo "Stopping infrastructure..."
	docker compose -f infra/docker-compose.yml down
	@echo "✓ Services stopped"

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
