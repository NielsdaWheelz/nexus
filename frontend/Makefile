.PHONY: help install dev build test lint format format-check clean

help:
	@echo "Frontend Makefile"
	@echo ""
	@echo "  make install      Install dependencies with pnpm"
	@echo "  make dev          Start development server (Next.js)"
	@echo "  make build        Build for production"
	@echo "  make test         Run tests (vitest)"
	@echo "  make lint         Run linter (eslint)"
	@echo "  make format       Auto-format code (prettier)"
	@echo "  make format-check Check formatting (prettier)"
	@echo "  make clean        Remove node_modules and dist"

PNPM := pnpm

install:
	@echo "Installing dependencies with pnpm..."
	$(PNPM) install
	@echo "✓ Dependencies installed"

dev: install
	@echo "Starting development server..."
	$(PNPM) run dev

build: install
	@echo "Building for production..."
	$(PNPM) run build
	@echo "✓ Build complete"

test: install
	@echo "Running tests..."
	$(PNPM) run test -- --run
	@echo "✓ Tests passed"

lint: install
	@echo "Running ESLint..."
	$(PNPM) run lint
	@echo "✓ Linting passed"

format: install
	@echo "Formatting code with Prettier..."
	$(PNPM) run format
	@echo "✓ Formatting complete"

format-check: install
	@echo "Checking formatting with Prettier..."
	$(PNPM) run format:check
	@echo "✓ Formatting check passed"

clean:
	@echo "Cleaning up..."
	rm -rf node_modules .next .pnpm-store pnpm-lock.yaml
	@echo "✓ Cleaned"
