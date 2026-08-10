.DEFAULT_GOAL := help

# The host port. An explicit `make ... PORT=9000`, or PORT in the environment, wins over a
# PORT in .env -- which is how compose resolves it too. Otherwise .env wins over this
# default, so the make targets and compose agree on which port they are talking about.
PORT ?= 8003
ifeq ($(filter-out default undefined file,$(origin PORT)),)
PORT_RESOLVED = $${PORT:-$(PORT)}
else
PORT_RESOLVED = $(PORT)
endif

# compose.yml is the base and holds the whole service definition. COMPOSE names an overlay
# layered on top of it, so a variant only has to carry what differs:
#   make docker-run COMPOSE=compose.ghcr.yml
COMPOSE ?= compose.yml
COMPOSE_FILES = -f compose.yml $(patsubst %,-f %,$(filter-out compose.yml,$(COMPOSE)))

# .env is optional — without it the repo's own config is used. It is sourced inside the
# recipe rather than expanded by make, so PORT and DATA_DIR resolve here the same way
# compose resolves them natively.
LOAD_ENV = set -a; [ -f .env ] && . ./.env; set +a; \
	export CLIMATE_SERVICE_CONFIG=$${CLIMATE_SERVICE_CONFIG:-./climate-service.yaml}; \
	export PORT=$(PORT_RESOLVED);

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

# TODO: decide whether a local venv is needed at all, or whether Docker is the only
# supported path. If Docker-only, run and upgrade go.
run: ## Start the service in a virtualenv, on http://127.0.0.1:8003
	@$(LOAD_ENV) HOST=127.0.0.1 uv run climate-service

docker-run: ## Start the service in Docker
	docker compose $(COMPOSE_FILES) up --build

docker-down: ## Stop the Docker service, leaving ./data in place
	docker compose $(COMPOSE_FILES) down

# ERA5-Land needs Copernicus CDS credentials: from .env if set, otherwise from the rc
# file the CDS docs tell you to create. Passed in for this command only, never baked in.
CDS_RC ?= $(HOME)/.ecmwfdatastoresrc

adopt-data: ## Repoint copied-in stores at this data directory, so they are served
	@$(LOAD_ENV) \
	if docker compose $(COMPOSE_FILES) exec -T api true 2>/dev/null; then \
		docker compose $(COMPOSE_FILES) exec -T api python - /app/data < adopt_data.py; \
	else \
		python3 adopt_data.py $${DATA_DIR:-data}; \
	fi

populate: ## Ingest the demo datasets, into the container if one is up, else the virtualenv
	@$(LOAD_ENV) \
	if [ -z "$$ECMWF_DATASTORES_KEY" ] && [ -f "$(CDS_RC)" ]; then \
		ECMWF_DATASTORES_URL=$$(sed -n 's/^url: *//p' "$(CDS_RC)"); \
		ECMWF_DATASTORES_KEY=$$(sed -n 's/^key: *//p' "$(CDS_RC)"); \
	fi; \
	export ECMWF_DATASTORES_URL ECMWF_DATASTORES_KEY; \
	[ -n "$$ECMWF_DATASTORES_KEY" ] || \
		echo "note: no CDS credentials in .env or $(CDS_RC) -- ERA5-Land will be skipped"; \
	if docker compose $(COMPOSE_FILES) exec -T api true 2>/dev/null; then \
		docker compose $(COMPOSE_FILES) exec -T \
			-e ECMWF_DATASTORES_URL -e ECMWF_DATASTORES_KEY \
			-e CHIRPS_START -e CHIRPS_END -e ERA5_START -e ERA5_END \
			api python - $(DATASETS) < populate.py; \
	else \
		uv run python populate.py $(DATASETS); \
	fi

# Exits nonzero if the instance turns out to be writable, so it can gate a deploy. Both
# signals have to say read-only: /info must report read_only true, and /manage must not be
# served. See "Read-only — not yet in effect" in README.md.
verify: ## Report what the running instance serves, failing if it is writable
	@$(LOAD_ENV) \
	base=http://127.0.0.1:$$PORT; \
	curl -sf -o /dev/null --max-time 5 $$base/health 2>/dev/null || { \
		echo "not running on $$base -- start it with 'make run' or 'make docker-run'"; exit 1; }; \
	get() { curl -sf --max-time 10 "$$1" 2>/dev/null || echo '{}'; }; \
	flag=$$(get $$base/info | python3 -c 'import sys,json;v=json.load(sys.stdin).get("read_only");print("absent" if v is None else str(v).lower())'); \
	printf 'read_only  : '; \
	case "$$flag" in \
		true) echo "true -- read-only mode in effect";; \
		false) echo "false -- turned off, instance is writable";; \
		*) echo "absent -- NOT ENFORCED, writable (upstream main lacks PR #329)";; \
	esac; \
	printf 'extent     : '; get $$base/extent | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d.get("name","?"), d.get("bbox","?"))'; \
	code=$$(curl -s -o /dev/null --max-time 10 -w '%{http_code}' $$base/manage); \
	printf 'manage     : '; \
	case "$$code" in \
		2??) echo "$$code served -- the console is reachable";; \
		401|403) echo "$$code refused -- writes are closed here";; \
		404) echo "404 absent -- no /manage on this build, read_only decides";; \
		3??) echo "$$code redirect -- inconclusive, read_only decides";; \
		000) echo "no response";; \
		*) echo "$$code -- unexpected, read_only decides";; \
	esac; \
	printf 'datasets   : '; get $$base/datasets | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("items",[])), "published")'; \
	why=; \
	[ "$$flag" = true ] || why="$$why /info does not report read_only=true;"; \
	case "$$code" in 2??) why="$$why /manage answered $$code;";; esac; \
	[ -z "$$why" ] || { \
		echo "FAIL: instance is writable --$$why do not expose it publicly"; exit 1; }; \
	echo "PASS: instance is read-only"

upgrade: ## Pull the latest open-climate-service and re-lock
	uv lock --upgrade-package open-climate-service
	uv sync

.PHONY: help run docker-run docker-down adopt-data populate verify upgrade
