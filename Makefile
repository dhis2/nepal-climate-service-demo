.DEFAULT_GOAL := help

PORT ?= 8003

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

install: ## Install dependencies with uv
	uv sync

run: ## Start the service (read-only, per climate-service.yaml)
	set -a && . ./.env && set +a && \
		uv run uvicorn open_climate_service.main:app --port $(PORT)

dev: ## Start with autoreload, for editing the config
	set -a && . ./.env && set +a && \
		uv run uvicorn open_climate_service.main:app --reload \
			--reload-include "*.yaml" --reload-include "*.yml" --port $(PORT)

upgrade: ## Pull the latest open-climate-service and re-lock
	uv lock --upgrade-package open-climate-service
	uv sync

docker-build: ## Build the container image
	docker compose build

docker-run: ## Start the service in Docker in the foreground
	docker compose up --build

docker-up: ## Start the service in Docker, detached
	docker compose up -d --build

docker-down: ## Stop the Docker service, keeping the data volume
	docker compose down

docker-logs: ## Follow the container logs
	docker compose logs -f

docker-shell: ## Shell into the running container, for operator tasks like ingestion
	docker compose exec api sh

verify: ## Check the instance is up, and report whether read-only is in effect
	@set -a && . ./.env 2>/dev/null || true; set +a; \
	base=http://127.0.0.1:$(PORT); \
	printf 'read_only  : '; curl -sf $$base/info | python3 -c 'import sys,json;v=json.load(sys.stdin).get("read_only");print(v if v is not None else "NOT ENFORCED -- writable (upstream main lacks PR #329)")'; \
	printf 'extent     : '; curl -sf $$base/extent | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["name"], d["bbox"])'; \
	printf 'ingest     : '; code=$$(curl -s -o /dev/null -w '%{http_code}' -X POST $$base/ingestions -H 'Content-Type: application/json' -d '{}'); \
		case $$code in 403) echo "$$code refused -- read-only in effect";; *) echo "$$code accepted -- instance is writable";; esac; \
	printf 'datasets   : '; curl -sf $$base/datasets | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("items",[])), "published")'

.PHONY: help install run dev upgrade docker-build docker-run docker-up docker-down docker-logs docker-shell verify
