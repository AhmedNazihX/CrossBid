# Crossbid — one entry point for both apps.
#
# backend/ and frontend/ are self-contained: each can be developed and tested on its own
# with its native tooling. These targets are the convenience layer over both, plus the
# checks CI runs (S0.1.4).

.DEFAULT_GOAL := help
SHELL := /bin/bash

BACKEND  := backend
FRONTEND := frontend
# `--env-file .env` is not optional: Compose resolves a bare `.env` relative to the compose
# file's own directory (infra/), which holds only .env.example, so without this every
# ${VAR} in docker-compose.yml is unset and `make dev` fails on the first required one.
COMPOSE  := docker compose --env-file .env -f infra/docker-compose.yml

.PHONY: help dev dev-api dev-web up down logs install test test-live lint lint-backend \
        lint-frontend format deps deps-check migrate seed-dev seed-demo demo-pack adversarial-pack extraction-fixtures eval \
        eval-db eval-db-stop eval-index eval-retrieval \
        build clean require-env

help: ## Show this help
	@echo "Crossbid — available targets:"
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "First run: cp infra/.env.example .env && make install"

# ---------------------------------------------------------------- development

require-env:
	@test -f .env || { echo "No .env found. Run: cp infra/.env.example .env"; exit 1; }

dev: require-env ## Start the whole stack in Docker (db + api + web)
	$(COMPOSE) up --build

up: require-env ## Start the stack detached
	$(COMPOSE) up --build -d

down: require-env ## Stop the stack (keeps the database volume)
	$(COMPOSE) down

logs: require-env ## Follow stack logs
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

test-db: ## Run only the tests that need a real Postgres (no LLM, no money). Needs DATABASE_URL.
	cd $(BACKEND) && uv run pytest -m database

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

seed-demo: ## Seed the demo GmbH: company, profile, and the ten documents, all `ready` (S2.4.3)
	cd $(BACKEND) && uv run python scripts/seed_demo_company.py

demo-pack: ## Rebuild the synthetic demo-company document pack (S6.3)
	cd $(BACKEND) && uv run python scripts/build_demo_company_pack.py

adversarial-pack: ## Rebuild the adversarial fixtures the injection guard is tested against (S6.5)
	cd $(BACKEND) && uv run python scripts/build_adversarial_pack.py

extraction-fixtures: ## Rebuild the synthetic extraction fixtures `recall.py` runs offline against (S3.2.3)
	cd $(BACKEND) && uv run python scripts/build_extraction_fixtures.py

eval: ## Assemble backend/evaluations/REPORT.md from the saved measurements. Offline, free
	cd $(BACKEND) && uv run python scripts/run_eval.py

EVAL_DB_NAME ?= crossbid-eval-db
EVAL_DB_PORT ?= 55432
EVAL_DB_URL  ?= postgresql://crossbid:crossbid@localhost:$(EVAL_DB_PORT)/crossbid_eval

eval-db: ## Start a throwaway pgvector for the retrieval eval and apply the migrations
	@docker rm -f $(EVAL_DB_NAME) >/dev/null 2>&1 || true
	docker run -d --name $(EVAL_DB_NAME) \
	  -e POSTGRES_USER=crossbid -e POSTGRES_PASSWORD=crossbid -e POSTGRES_DB=crossbid_eval \
	  -p $(EVAL_DB_PORT):5432 pgvector/pgvector:pg16 >/dev/null
	@printf 'waiting for postgres'; \
	  for i in $$(seq 1 60); do \
	    docker exec $(EVAL_DB_NAME) pg_isready -U crossbid -d crossbid_eval >/dev/null 2>&1 \
	      && { echo ' ready'; break; }; \
	    printf '.'; sleep 1; \
	  done
	cd $(BACKEND) && DATABASE_URL=$(EVAL_DB_URL) uv run python scripts/migrate.py

eval-db-stop: ## Remove the throwaway eval database
	docker rm -f $(EVAL_DB_NAME)

eval-index: ## Index the three golden packs into the throwaway (costs ~1 cent of embeddings)
	cd $(BACKEND) && DATABASE_URL=$(EVAL_DB_URL) uv run python scripts/index_pack.py de fr en

eval-retrieval: ## Ask the retrieval key and score it with ragas (costs money)
	cd $(BACKEND) && DATABASE_URL=$(EVAL_DB_URL) uv run python scripts/run_retrieval_eval.py de fr en
	cd $(BACKEND) && uv run python scripts/score_retrieval.py de fr en

# ---------------------------------------------------------------- build

build: require-env ## Build both Docker images
	$(COMPOSE) build

clean: ## Remove build artefacts and caches (keeps .env and the database volume)
	rm -rf $(BACKEND)/.venv $(BACKEND)/.pytest_cache $(BACKEND)/.ruff_cache
	rm -rf $(FRONTEND)/node_modules $(FRONTEND)/.next
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
