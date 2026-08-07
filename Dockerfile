FROM ghcr.io/astral-sh/uv:0.12-python3.12-trixie-slim

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV PYTHONDONTWRITEBYTECODE=1
# matplotlib needs a writable config dir as non-root
ENV MPLCONFIGDIR=/tmp

# git: the dependency is fetched from a git URL, see [tool.uv.sources] in pyproject.toml
# curl: HEALTHCHECK
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends git curl && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 999 ocs && \
    useradd --no-create-home --shell /usr/sbin/nologin --uid 999 --gid 999 ocs

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY climate-service.yaml ./

# data_dir is ./data, so /app/data. A bind mount masks this, and the service creates what
# it needs at runtime — this only seeds a named volume, which inherits the ownership.
RUN mkdir -p /app/data/artifacts /app/data/jobs /app/data/openeo_jobs && \
    printf '[]\n' > /app/data/artifacts/records.json && \
    chown -R ocs:ocs /app/data

ENV CLIMATE_SERVICE_CONFIG=/app/climate-service.yaml
ENV PORT=8003
ENV PATH="/app/.venv/bin:$PATH"

USER ocs

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

CMD ["climate-service"]
