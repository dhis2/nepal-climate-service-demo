# `main` is upstream's only published tag, and it moves. Pin a digest when this
# instance needs to sit on a known build.
FROM ghcr.io/dhis2/open-climate-service:main

# Also bind-mounted by compose, so both can be edited without a rebuild.
COPY climate-service.yaml /app/climate-service.yaml
COPY plugins/ /app/plugins/

ENV CLIMATE_SERVICE_CONFIG=/app/climate-service.yaml
ENV PORT=8003
