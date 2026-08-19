.DEFAULT_GOAL := help

PORT ?= 8003

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

docker-build: ## Build the container image
	docker compose build

docker-run: ## Start the container in the foreground
	docker compose up

test: ## Run the plugin contract checks (no network, no credentials)
	docker compose run --rm --no-deps --user root -v $(CURDIR)/tests:/app/tests:ro api \
		sh -c 'uv pip install --python /app/.venv/bin/python -q pytest pyyaml && \
			PYTHONPATH=/app/plugins python -m pytest /app/tests -q'

verify: ## Check the instance is up and actually read-only
	@base=http://127.0.0.1:$(PORT); \
	printf 'read_only  : '; curl -sf $$base/info | python3 -c 'import sys,json;print(json.load(sys.stdin)["read_only"])'; \
	printf 'extent     : '; curl -sf $$base/extent | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["name"], d["bbox"])'; \
	printf 'ingest 403 : '; test "$$(curl -s -o /dev/null -w '%{http_code}' -X POST $$base/ingestions -H 'Content-Type: application/json' -d '{}')" = 403 && echo yes || echo "NO -- instance is writable!"; \
	printf 'datasets   : '; curl -sf $$base/datasets | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("items",[])), "published")'

.PHONY: help docker-build docker-run test verify
