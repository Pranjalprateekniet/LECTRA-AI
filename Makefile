# ==============================================================================
# Makefile - Revision RAG Local Development (Host)
# ==============================================================================
# Lectra runs directly on the host machine using the project Python virtual
# environment (.venv) and pip for dependency management. Docker is not used.

SHELL := /bin/bash
PYTHON_BIN := .venv/bin/python
PYTEST := .venv/bin/pytest
RUFF := .venv/bin/ruff
ALEMBIC := .venv/bin/alembic
NPM := npm --prefix frontend

.PHONY: help install test lint format run-backend run-worker run-worker-once run-frontend migrate clean

help:
	@echo "Available commands:"
	@echo "  --- Local Development (Host) ---"
	@echo "  make install        - Install backend/core (via pip in .venv) and frontend dependencies"
	@echo "  make test           - Run backend and core unit tests with pytest"
	@echo "  make lint           - Run python linting (ruff) and frontend linting (eslint)"
	@echo "  make format         - Format python codebase with ruff"
	@echo "  make run-backend    - Start FastAPI development server on port 8000"
	@echo "  make run-worker     - Start standalone ingestion worker daemon"
	@echo "  make run-worker-once- Run standalone ingestion worker once and exit"
	@echo "  make run-frontend   - Start Next.js development server on port 3000"
	@echo "  make migrate        - Run database migrations via Alembic"
	@echo "  make clean          - Clean bytecode, caches and build artifacts"

# --- Local Development Targets ---

install:
	@echo "Installing python packages into .venv environment using pip..."
	$(PYTHON_BIN) -m pip install --upgrade pip
	$(PYTHON_BIN) -m pip install -r requirements-dev.txt
	@echo "Installing frontend dependencies with npm..."
	$(NPM) ci

test:
	@echo "Running tests in .venv environment..."
	$(PYTEST) -v

lint:
	@echo "Linting python codebase..."
	$(RUFF) check .
	@echo "Linting frontend codebase..."
	$(NPM) run lint

format:
	@echo "Formatting python codebase..."
	$(RUFF) format .
	$(RUFF) check --fix .

run-backend:
	@echo "Starting FastAPI backend server on http://127.0.0.1:8000..."
	$(PYTHON_BIN) -m lectra_backend.main

run-worker:
	@echo "Starting standalone ingestion worker..."
	$(PYTHON_BIN) -m lectra_core.worker

run-worker-once:
	@echo "Running standalone ingestion worker once..."
	$(PYTHON_BIN) -m lectra_core.worker --once

run-frontend:
	@echo "Starting Next.js frontend on http://localhost:3000..."
	$(NPM) run dev

migrate:
	@echo "Applying Alembic migrations..."
	$(ALEMBIC) -c core/alembic.ini upgrade head

clean:
	@echo "Cleaning temporary files and caches..."
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type f -name "*.py[cod]" -delete
