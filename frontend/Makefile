.PHONY: help install dev build test lint format format-check clean

help:
	@echo "Frontend Makefile"
	@echo ""
	@echo "  make install      Install dependencies with bun"
	@echo "  make dev          Start development server (Vite)"
	@echo "  make build        Build for production"
	@echo "  make test         Run tests (vitest)"
	@echo "  make lint         Run linter (eslint)"
	@echo "  make format       Auto-format code (prettier)"
	@echo "  make format-check Check formatting (prettier)"
	@echo "  make clean        Remove node_modules and dist"

BUN := bun

install:
	@echo "Installing dependencies with bun..."
	$(BUN) install
	@echo "✓ Dependencies installed"

dev: install
	@echo "Starting development server..."
	$(BUN) run dev

build: install
	@echo "Building for production..."
	$(BUN) run build
	@echo "✓ Build complete"

test: install
	@echo "Running tests..."
	$(BUN) test
	@echo "✓ Tests passed"

lint: install
	@echo "Running ESLint..."
	$(BUN) run lint
	@echo "✓ Linting passed"

format: install
	@echo "Formatting code with Prettier..."
	$(BUN) run format
	@echo "✓ Formatting complete"

format-check: install
	@echo "Checking formatting with Prettier..."
	$(BUN) run format-check
	@echo "✓ Formatting check passed"

clean:
	@echo "Cleaning up..."
	rm -rf node_modules dist build .cache bun.lock
	@echo "✓ Cleaned"
