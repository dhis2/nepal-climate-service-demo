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

verify: ## Check the instance is up and actually read-only
	@set -a && . ./.env && set +a && \
	base=http://127.0.0.1:$(PORT); \
	printf 'read_only  : '; curl -sf $$base/info | python3 -c 'import sys,json;print(json.load(sys.stdin)["read_only"])'; \
	printf 'extent     : '; curl -sf $$base/extent | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["name"], d["bbox"])'; \
	printf 'ingest 403 : '; test "$$(curl -s -o /dev/null -w '%{http_code}' -X POST $$base/ingestions -H 'Content-Type: application/json' -d '{}')" = 403 && echo yes || echo "NO -- instance is writable!"; \
	printf 'datasets   : '; curl -sf $$base/datasets | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("items",[])), "published")'

.PHONY: help install run dev upgrade verify
