FROM ghcr.io/astral-sh/uv:0.12-python3.12-trixie-slim

# Compile bytecode into the venv for faster startup, and don't write .pyc at runtime
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV PYTHONDONTWRITEBYTECODE=1
# matplotlib wants a writable config dir, and the service runs as a non-root user
ENV MPLCONFIGDIR=/tmp

# git: open-climate-service is resolved from a git URL, see [tool.uv.sources]
# curl: HEALTHCHECK
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install -y --no-install-recommends git curl

RUN groupadd --gid 999 ocs && \
    useradd --no-create-home --shell /usr/sbin/nologin --uid 999 --gid 999 ocs

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY climate-service.yaml ./

# data_dir is ./data, i.e. /app/data. Normally masked by the bind mount in compose.yml;
# this only makes the image runnable on its own.
RUN mkdir -p /app/data && chown -R ocs:ocs /app/data

ENV CLIMATE_SERVICE_CONFIG=/app/climate-service.yaml
ENV PORT=8003
ENV PATH="/app/.venv/bin:$PATH"

USER ocs

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Exec form, so the server is PID 1 and gets signals directly. The entry point reads
# HOST and PORT from the environment; HOST defaults to 0.0.0.0.
CMD ["climate-service"]
