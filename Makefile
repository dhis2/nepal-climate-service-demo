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
	@$(LOAD_ENV) HOST=127.0.0.1 PORT=$(PORT) uv run climate-service

docker-run: ## Start the service in Docker
	docker compose -f $(COMPOSE) up --build

docker-down: ## Stop the Docker service, keeping the data volume
	docker compose -f $(COMPOSE) down

# ERA5-Land needs Copernicus CDS credentials: from .env if set, otherwise from the rc
# file the CDS docs tell you to create. Passed in for this command only, never baked in.
CDS_RC ?= $(HOME)/.ecmwfdatastoresrc

adopt-data: ## Repoint copied-in stores at this data directory, so they are served
	@docker compose -f $(COMPOSE) exec -T api python - /app/data < adopt_data.py 2>/dev/null \
		|| python3 adopt_data.py $${DATA_DIR:-data}

populate: ## Ingest the demo datasets, into the container if one is up, else the virtualenv
	@$(LOAD_ENV) \
	if [ -z "$$ECMWF_DATASTORES_KEY" ] && [ -f "$(CDS_RC)" ]; then \
		ECMWF_DATASTORES_URL=$$(sed -n 's/^url: *//p' "$(CDS_RC)"); \
		ECMWF_DATASTORES_KEY=$$(sed -n 's/^key: *//p' "$(CDS_RC)"); \
	fi; \
	export ECMWF_DATASTORES_URL ECMWF_DATASTORES_KEY; \
	[ -n "$$ECMWF_DATASTORES_KEY" ] || \
		echo "note: no CDS credentials in .env or $(CDS_RC) -- ERA5-Land will be skipped"; \
	if docker compose -f $(COMPOSE) exec -T api true 2>/dev/null; then \
		docker compose -f $(COMPOSE) exec -T \
			-e ECMWF_DATASTORES_URL -e ECMWF_DATASTORES_KEY \
			api python - $(DATASETS) < populate.py; \
	else \
		uv run python populate.py $(DATASETS); \
	fi

verify: ## Report what the running instance serves
	@$(LOAD_ENV) \
	base=http://127.0.0.1:$(PORT); \
	curl -sf -o /dev/null --max-time 5 $$base/health 2>/dev/null || { \
		echo "not running on $$base -- start it with 'make run' or 'make docker-run'"; exit 1; }; \
	get() { curl -sf --max-time 10 "$$1" 2>/dev/null || echo '{}'; }; \
	printf 'read_only  : '; get $$base/info | python3 -c 'import sys,json;v=json.load(sys.stdin).get("read_only");print(v if v is not None else "NOT ENFORCED -- writable (upstream main lacks PR #329)")'; \
	printf 'extent     : '; get $$base/extent | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("name","?"), d.get("bbox","?"))'; \
	printf 'manage     : '; code=$$(curl -s -o /dev/null --max-time 10 -w '%{http_code}' $$base/manage); \
		case $$code in 403) echo "403 refused -- read-only in effect";; 000) echo "no response";; *) echo "$$code reachable -- instance is writable";; esac; \
	printf 'datasets   : '; get $$base/datasets | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("items",[])), "published")'

upgrade: ## Pull the latest open-climate-service and re-lock
	uv lock --upgrade-package open-climate-service
	uv sync

.PHONY: help run docker-run docker-down adopt-data populate verify upgrade
