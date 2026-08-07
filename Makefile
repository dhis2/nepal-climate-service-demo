.DEFAULT_GOAL := help

PORT ?= 8003

# compose.yml builds from this repo's pin; compose.ghcr.yml pulls the published image:
#   make docker-run COMPOSE=compose.ghcr.yml
COMPOSE ?= compose.yml

# .env is optional — without it the repo's own config is used.
LOAD_ENV = set -a; [ -f .env ] && . ./.env; set +a; \
	export CLIMATE_SERVICE_CONFIG=$${CLIMATE_SERVICE_CONFIG:-climate-service.yaml};

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

# TODO: decide whether a local venv is needed at all, or whether Docker is the only
# supported path. If Docker-only, run and upgrade go.
run: ## Start the service in a virtualenv, on http://127.0.0.1:8003
	@$(LOAD_ENV) uv run uvicorn open_climate_service.main:app --port $(PORT)

docker-run: ## Start the service in Docker
	docker compose -f $(COMPOSE) up --build

docker-down: ## Stop the Docker service, keeping the data volume
	docker compose -f $(COMPOSE) down

verify: ## Report what the running instance serves
	@$(LOAD_ENV) \
	base=http://127.0.0.1:$(PORT); \
	printf 'read_only  : '; curl -sf $$base/info | python3 -c 'import sys,json;v=json.load(sys.stdin).get("read_only");print(v if v is not None else "NOT ENFORCED -- writable (upstream main lacks PR #329)")'; \
	printf 'extent     : '; curl -sf $$base/extent | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["name"], d["bbox"])'; \
	printf 'ingest     : '; code=$$(curl -s -o /dev/null -w '%{http_code}' -X POST $$base/ingestions -H 'Content-Type: application/json' -d '{}'); \
		case $$code in 403) echo "$$code refused -- read-only in effect";; *) echo "$$code accepted -- instance is writable";; esac; \
	printf 'datasets   : '; curl -sf $$base/datasets | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("items",[])), "published")'

upgrade: ## Pull the latest open-climate-service and re-lock
	uv lock --upgrade-package open-climate-service
	uv sync

.PHONY: help run docker-run docker-down verify upgrade
