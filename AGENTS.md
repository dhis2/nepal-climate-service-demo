# Nepal Climate Service demo

Agent context for the `nepal-climate-service-demo` repository. Provider-agnostic -- intended to be readable by any AI coding assistant.

The conventions at the bottom are taken from [open-climate-service/AGENTS.md](https://github.com/dhis2/open-climate-service/blob/main/AGENTS.md) and are identical to it. Where the two files disagree about anything else, that one describes the service and this one describes this instance.

## What this repository is

A deployment, not a codebase. It holds the configuration for one public Open Climate Service instance -- the Nepal extent, kept online as a stable demo endpoint (CLIM-848) -- and nothing that belongs in the service itself.

If a change would be useful to any other instance, it belongs upstream in [open-climate-service](https://github.com/dhis2/open-climate-service), not here.

Key facts an agent will otherwise get wrong:

- **There is no application code.** `open-climate-service` is a dependency, pinned in `pyproject.toml`. Do not vendor, patch or reimplement it here.
- **The instance is read-only.** `climate-service.yaml` sets `read_only: true`: ingestion, sync, `/manage`, stored process graphs and batch jobs are refused; the catalogue, the data endpoints, the map viewer and synchronous `POST /result` stay open. Ingestion is an operator task run on the host.
- **`read_only` is an ordinary config key.** A build of open-climate-service that predates read-only mode ignores it in silence and serves a fully writable public instance. Never assume it took effect -- `make verify` asserts it against a running instance.
- **Almost everything served is built in.** The 16 built-in dataset templates cover what the demo needs. There is exactly one instance plugin, `plugins/datasets/clms_gpp.py`, and it is there because it exercises a dekadal cadence and a credentialed S3 source that no built-in dataset does. Adding a second plugin needs a reason of that kind.

## Layout

```
climate-service.yaml    # the instance: extent, data_dir, read_only, plugins_dir
plugins/datasets/       # instance plugins (clms_gpp.py, clms_gpp.yaml)
tests/                  # plugin contract checks -- no network, no credentials
Dockerfile              # FROM upstream's published image; adds config, plugins, port
compose.yml             # host bind mounts for config, plugins and ./data
Makefile                # install, run, dev, test, upgrade, verify
pyproject.toml/uv.lock  # the pin; governs the virtualenv path only
data/                   # ingested GeoZarr stores, gitignored, host-owned
```

## Running it

```bash
docker compose up -d --build   # http://127.0.0.1:8003, needs no .env
make verify                    # assert it is up and actually refusing writes
```

Or in a virtualenv:

```bash
cp .env.example .env
make install
make run
make test                      # plugin contract checks
```

The Docker image is `FROM ghcr.io/dhis2/open-climate-service:main`, so the dependency install, the non-root `ocs` user, `WORKDIR` and the `HEALTHCHECK` all come from upstream and are not repeated here. `main` is upstream's only published tag and it moves; pin a digest when the instance needs to sit on a known build.

`climate-service.yaml`, `plugins/` and `./data` are bind-mounted from the host. Both of the first two are also baked into the image so it runs standalone -- keep those in step: **anything `climate-service.yaml` points at must reach the container by both routes.** A missing `plugins_dir` is only a startup WARNING, but `GET /dataset-templates/` then returns 500 while the healthcheck stays green.

## Changing the instance

- **Editing `climate-service.yaml`** is the main thing this repo is for. Restart to pick it up; `make dev` autoreloads on YAML changes.
- **Changing the pin** means `make upgrade`, which re-locks and re-syncs. The container does not use `uv.lock` -- it follows upstream's published image -- so a pin change and an image change are two separate things.
- **After any deploy**, run `make verify`. A green healthcheck proves the process is listening, not that the instance is configured as intended.

## Data

Read-only applies to HTTP, so ingestion happens on the host and the stores are copied into `./data`. The container runs as uid 999; on Linux `chown -R 999:999 data` before starting, while Docker Desktop on macOS remaps ownership itself. ERA5-Land needs Copernicus CDS credentials; CHIRPS3 and WorldPop are public; the CLMS GPP plugin needs CDSE S3 keys.

Never commit credentials, and never commit anything under `data/`.

## Commit conventions

- **Conventional Commits** for all git activity -- commit messages, branch names, and PR titles.
  - Format: `<type>(<scope>)?: <description>` (e.g. `feat(ci): add docker publish workflow`, `fix(main): correct db path creation`).
  - Types: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `build`, `perf`, `style`, `revert`.
  - Branch names: `<type>/<short-description>` (e.g. `feat/makefile-and-ci`, `fix/sqlite-path`).
- **No attribution.** Do not add `Co-Authored-By: Claude ...`, "Generated with Claude Code", or any similar attribution to commits, PRs, or files.
- **No emojis** anywhere -- not in commits, code, comments, or documentation.
