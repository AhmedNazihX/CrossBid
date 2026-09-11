# Crossbid — one entry point for both apps.
#
# backend/ and frontend/ are self-contained: each can be developed and tested on its own
# with its native tooling. These targets are the convenience layer over both, plus the
# checks CI runs (S0.1.4).

.DEFAULT_GOAL := help
SHELL := /bin/bash

BACKEND  := backend
FRONTEND := frontend
COMPOSE  := docker compose -f infra/docker-compose.yml

.PHONY: help dev dev-api dev-web up down logs install test test-live lint lint-backend \
        lint-frontend format deps deps-check migrate seed-dev demo-pack eval build clean

help: ## Show this help
	@echo "Crossbid — available targets:"
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "First run: cp infra/.env.example .env && make install"

# ---------------------------------------------------------------- development

dev: ## Start the whole stack in Docker (db + api + web)
	@test -f .env || { echo "No .env found. Run: cp infra/.env.example .env"; exit 1; }
	$(COMPOSE) up --build

up: ## Start the stack detached
	@test -f .env || { echo "No .env found. Run: cp infra/.env.example .env"; exit 1; }
	$(COMPOSE) up --build -d

down: ## Stop the stack (keeps the database volume)
	$(COMPOSE) down

logs: ## Follow stack logs
	$(COMPOSE) logs -f

dev-api: ## Run the API on the host with reload, against the Compose database
	cd $(BACKEND) && uv run uvicorn crossbid.main:app --reload --port 8000

dev-web: ## Run the web app on the host with reload
	cd $(FRONTEND) && npm run dev

install: ## Install dependencies for both apps
	cd $(BACKEND) && uv sync --extra dev
	cd $(FRONTEND) && npm install

# ---------------------------------------------------------------- quality

lint: lint-backend lint-frontend deps-check ## Lint and type-check both apps, and check the manifest

lint-backend: ## ruff + pyright
	cd $(BACKEND) && uv run ruff check .
	cd $(BACKEND) && uv run ruff format --check .
	cd $(BACKEND) && uv run pyright

lint-frontend: ## eslint + tsc
	@test -d $(FRONTEND)/node_modules || { echo "frontend deps missing. Run: make install"; exit 1; }
	cd $(FRONTEND) && npm run lint
	cd $(FRONTEND) && npm run format:check
	cd $(FRONTEND) && npm run typecheck

format: ## Apply formatting to both apps
	cd $(BACKEND) && uv run ruff format . && uv run ruff check --fix .
	cd $(FRONTEND) && npm run format

test: ## Run tests, excluding those marked `live`
	cd $(BACKEND) && uv run pytest

test-live: ## Run only the tests that hit real services or an LLM (costs money)
	cd $(BACKEND) && uv run pytest -m live

# ---------------------------------------------------------------- dependencies

deps: ## Regenerate dependencies.txt from both lock files
	python3 scripts/gen_dependencies.py

deps-check: ## Fail if dependencies.txt has drifted from the lock files
	python3 scripts/gen_dependencies.py --check

# ---------------------------------------------------------------- data and evaluation

migrate: ## Apply database migrations
	@test -f $(BACKEND)/scripts/migrate.py \
	  || { echo "Not built yet: the migration runner lands with story S0.2.1."; exit 1; }
	cd $(BACKEND) && uv run python scripts/migrate.py

seed-dev: ## Create the dev company row (idempotent) and print NEXT_PUBLIC_DEV_COMPANY_ID
	cd $(BACKEND) && uv run python scripts/seed_dev_company.py

demo-pack: ## Rebuild the synthetic demo-company document pack (S6.3)
	cd $(BACKEND) && uv run python scripts/build_demo_company_pack.py

eval: ## Run the evaluation suite and write evaluations/REPORT.md
	@test -f $(BACKEND)/scripts/run_eval.py \
	  || { echo "Not built yet: the evaluation suite lands with story S7.1."; exit 1; }
	cd $(BACKEND) && uv run python scripts/run_eval.py

# ---------------------------------------------------------------- build

build: ## Build both Docker images
	$(COMPOSE) build

clean: ## Remove build artefacts and caches (keeps .env and the database volume)
	rm -rf $(BACKEND)/.venv $(BACKEND)/.pytest_cache $(BACKEND)/.ruff_cache
	rm -rf $(FRONTEND)/node_modules $(FRONTEND)/.next
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
