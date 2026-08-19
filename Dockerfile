# `main` is upstream's only published tag, and it moves. Pin a digest when this
# instance needs to sit on a known build.
FROM ghcr.io/dhis2/open-climate-service:main

# The image brings the service and its dependencies; pyproject.toml brings what the
# instance plugins add on top.
USER root
COPY pyproject.toml ./
RUN uv pip install --python /app/.venv/bin/python -r pyproject.toml
USER ocs

# Also bind-mounted by compose, so both can be edited without a rebuild.
COPY climate-service.yaml /app/climate-service.yaml
COPY plugins/ /app/plugins/

ENV CLIMATE_SERVICE_CONFIG=/app/climate-service.yaml
ENV PORT=8003
