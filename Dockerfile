# Upstream's published image, not a build of our own: it already installs the service,
# creates the non-root `ocs` user it runs as, sets WORKDIR /app and defines a HEALTHCHECK.
# None of that is repeated here, and this repo's pyproject.toml/uv.lock govern only the
# virtualenv path.
#
# `main` is the only tag upstream publishes -- there is no release yet. It moves, so pin
# the digest here once this instance needs to stay on a known build.
FROM ghcr.io/dhis2/open-climate-service:main

# Baked in so the image also runs standalone. compose.yml mounts the host copy over this,
# so the config can be edited without a rebuild.
COPY climate-service.yaml /app/climate-service.yaml

ENV CLIMATE_SERVICE_CONFIG=/app/climate-service.yaml
ENV PORT=8003
