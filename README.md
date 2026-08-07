# Nepal Climate Service — public demo instance

A publicly reachable [Open Climate Service](https://github.com/dhis2/open-climate-service)
instance configured to the Nepal extent, kept online as a stable demo endpoint.

Tracked in [CLIM-848](https://dhis2.atlassian.net/browse/CLIM-848).

## What it's for

- **Try Open Climate Service without deploying it.** Browse the STAC catalogue, the map
  viewer and the data endpoints against real data — no local install, no ingest.
- **Test client integrations against a real endpoint.** The
  [GeoLibre plugin](https://github.com/dhis2/open-climate-service-geolibre-plugin),
  [STAC Browser](https://github.com/radiantearth/stac-browser) and any openEO client just
  need a URL.
- **A stable reference** for docs, screenshots, onboarding and reproducing bug reports.

Nepal's terrain and monsoon climate make it a good showcase for temperature and
precipitation, and the country extent keeps the ingested stores small.

## Stock Open Climate Service, deliberately

This instance ships **no custom datasets, processes or workflows** — there is no
`plugins_dir`. Everything it serves is built in, so what you see here is what a stock
install does. That also means there is nothing instance-specific to keep working as the
core service moves.

Available from the built-in templates:

| Source | Datasets |
| ------ | -------- |
| ERA5-Land | 2m temperature and precipitation — daily, monthly, and local-time-from-hourly variants |
| CHIRPS3 | Daily precipitation |
| WorldPop | Total population, population by age and sex, population change |
| Normals | 1991–2020 daily and monthly climatological normals for ERA5-Land and CHIRPS3 |

`GET /dataset-templates/` lists them all with their parameters.

## Read-only — not yet in effect

`climate-service.yaml` sets `read_only: true`, but **this instance is currently writable.**
Read-only mode is unmerged upstream (PR #329) and config there is read as a plain dict, so
the key is ignored rather than rejected: every write endpoint is served, including
ingestion, sync, batch jobs and the `/manage` console.

**Do not expose it publicly as it stands** — keep it private or behind an allowlist proxy
until #329 lands. The key is kept rather than deleted because it takes effect on its own
once that happens. What it will do then:

| | |
| --- | --- |
| **Open** | `/collections`, `/stac`, `/datasets`, `/processes`, `/process_graphs`, `/extent`, `/zarr/…`, `/icechunk/…`, the landing page, `/map`, and `POST /result` |
| **Refused (403)** | ingestion and sync, the `/manage` console, `PUT`/`DELETE /process_graphs/{id}`, and batch jobs |

`POST /result` stays open because it is how the instance is actually used — it is a POST
only because the process graph travels in the body, and it cannot publish a dataset. Batch
jobs close entirely: there is no request identity, so the job namespace would be shared
between visitors.

`make verify` reports the current state — run it after every deploy and every
`make upgrade`, since the pin tracks a moving branch.

## Running it

In Docker:

```bash
make docker-run           # http://127.0.0.1:8003
make verify               # in another shell — reports what the instance serves
make docker-down
```

Or in a virtualenv:

```bash
make run                  # http://127.0.0.1:8003
make verify
```

No setup step either way: `uv run` syncs the environment itself, and the config in this
repo is used by default. Copy `.env.example` to `.env` only to point
`CLIMATE_SERVICE_CONFIG` somewhere else or to set `CLIMATE_SERVICE_BASE_URL`.

### Which image

`make docker-run` builds from `uv.lock`, so the container is the exact commit this repo
pins and it never moves on its own. To run the image upstream publishes instead, without
building:

```bash
make docker-run COMPOSE=compose.ghcr.yml
```

That pulls `ghcr.io/dhis2/open-climate-service:main`, which tracks upstream's `main` and
moves when upstream does — it re-pulls on every start rather than reusing a stale cache.
It is `linux/amd64` only, so it runs emulated on arm64. `COMPOSE=compose.ghcr.yml` works
with `docker-down` too.

Both run as the `ocs` user (uid/gid 999). For operator tasks, `docker compose exec api sh`
gets you a shell inside.

### Where the data lives

`./data` on the host is bind-mounted to `/app/data` in the container, so the stores the
instance serves are ordinary files you can reach. That is the point: data can be produced
somewhere else and copied in, which is the expected path for a read-only instance that
never ingests anything itself.

```bash
scp -r data/* server:/srv/nepal-climate-service-demo/data/
make adopt-data           # repoint the registry at this directory
```

Point somewhere else with `DATA_DIR=/srv/climate-data make docker-run`.

**Copy the whole data directory, not just the stores.** `data/artifacts/records.json` is
the registry — there is no directory scan, so a store copied in without its record is
never discovered. **No restart is needed**: the lookup is cached against that file's mtime
(`services.py:623`), so writing it invalidates the cache and the next request picks the
change up.

**`make adopt-data` is not optional when data comes from elsewhere.** The registry in
`data/artifacts/records.json` stores *resolved absolute* paths — `services.py:405` writes
`str(store_path.resolve())`, and `services.py:1167` decides whether a dataset is published
by testing that exact path exists. Stores ingested in a container are recorded under
`/app/data`, so on a host expecting `/srv/climate-data` every one of them fails that test
and the catalogue comes up **empty, with no error**. The same bites moving between the
container and a virtualenv, whose data directories differ. `adopt-data` rewrites `path` and
`asset_paths` to the directory the data is actually in; it runs inside the container when
one is up, and against `./data` otherwise.

**Ownership differs by platform.** Docker Desktop on macOS remaps ownership, so the
container reads and writes host files whatever they are owned by. On Linux the host uid is
preserved, and the container runs as 999 — so `chown -R 999:999 data` on the host, or the
service cannot write, and cannot read files that are not world-readable.

Alternating between the container and the virtualenv leaves duplicate records pointing at
each path. Nothing breaks — the service logs `Ignoring stale artifact … backing storage is
missing` and skips them — but the registry accumulates cruft, so it is worth settling on
one runtime.

Once read-only mode is in effect the mount can be `:ro`, which makes the guarantee
structural rather than a config key: nothing in the container could write to the stores
even if it tried. It is left writable for now because `make populate` needs to write.

## Ingesting data

With the instance running, `make populate` ingests a representative demo set — enough that
the catalogue isn't empty, small enough to stay cheap:

```bash
make docker-run           # in one shell
make populate             # in another
```

| Dataset | Range | Credentials |
| ------- | ----- | ----------- |
| `chirps3_precipitation_daily` | 2026-05-01 → 2026-05-31 | none |
| `worldpop_population_global2_R2025A_100m` | 2020 → 2025 | none |
| `era5land_temperature_monthly` | 2020-01 → 2024-12 | CDS |
| `era5land_precipitation_monthly` | 2020-01 → 2024-12 | CDS |
| `era5land_temperature_monthly_normal_1991_2020` | its own 1991–2020 period | CDS |

The list lives in `populate.py`, which is piped into the container rather than baked into
the image. Ingest a subset with `make populate DATASETS=chirps3_precipitation_daily`, and
override ranges with `CHIRPS_START`, `CHIRPS_END`, `ERA5_START`, `ERA5_END`.

The ERA5-Land rows need a **Copernicus CDS** key — get one from your profile at
[cds.climate.copernicus.eu](https://cds.climate.copernicus.eu) and accept the licence for
each ERA5-Land dataset. `make populate` reads it from `ECMWF_DATASTORES_URL` and
`ECMWF_DATASTORES_KEY` in `.env`, falling back to `~/.ecmwfdatastoresrc`:

```
url: https://cds.climate.copernicus.eu/api
key: your-api-key
```

Without credentials, the ERA5-Land rows are skipped with a note and the public ones still
run. CHIRPS3 and WorldPop need nothing.

Ingestion is an operator task rather than an HTTP one. The ingestion endpoints happen to be
reachable on the current pin, but keeping ingestion out of the request path is what lets
read-only be absolute once it is in effect, with no exemption, token or trusted header that
could be misconfigured into a bypass. A supported CLI is
[CLIM-862](https://dhis2.atlassian.net/browse/CLIM-862).

For scale: a fuller Nepal instance holds ~3.6 GB across 11 stores, dominated by a 3.1 GB
Copernicus DEM. This demo has no DEM, so expect well under 1 GB.

## Deployment notes

- **Pin to a release once one exists.** `pyproject.toml` tracks git `main` because upstream
  has published no tags and no releases at all, so there is nothing to pin to yet. The
  dependency therefore moves underneath you: re-run `make verify` after every
  `make upgrade`. See the TODO in `pyproject.toml`.
- **Set `CLIMATE_SERVICE_BASE_URL`** to the public HTTPS URL, or STAC and openEO links will
  point at the internal host.
- **CORS** is already permissive on the data and STAC routes, which is what browser clients
  (GeoLibre, STAC Browser, the openEO editor) need cross-origin.
- **The reverse proxy is currently load-bearing for integrity, not just availability.**
  With read-only not yet in effect, an allowlist proxy is the only thing that would keep
  the write endpoints closed. And even once read-only lands, `POST /result` remains an
  unbounded compute endpoint. A public deployment should sit behind a proxy that allowlists
  the open routes — an allowlist, not a denylist, so routes added in a later release aren't
  permitted by default — and applies request timeouts, body-size limits and per-IP rate
  limiting. Tracked as [CLIM-864](https://dhis2.atlassian.net/browse/CLIM-864).
- Restricting execution to specific workflows is [CLIM-863](https://dhis2.atlassian.net/browse/CLIM-863).

Hosting and provisioning is [CLIM-857](https://dhis2.atlassian.net/browse/CLIM-857).

## Open questions

Decisions this repo has taken provisionally, and should settle deliberately.

### Is a local virtualenv path needed at all?

`make run` and `make upgrade` exist alongside the Docker path, and `.python-version` plus the
`>=3.12,<3.13` bound in `pyproject.toml` serve only the virtualenv — the image pins Python
through its base image. If deployment is Docker-only, all of that can go and the repo becomes a
Dockerfile, two compose files and a config. If the virtualenv stays, it needs to be because
someone actually develops against it.

### Upstream publishes no versioned artifacts

There are no git tags and no releases, and `ghcr.io/dhis2/open-climate-service` has exactly one
real tag, `main`, rebuilt on every push — no `latest`, no semver. So `pyproject.toml` tracks a
branch and `compose.ghcr.yml` tracks a moving image; neither can be pinned to a version because
no version exists. A demo instance wants the opposite. Worth asking upstream for `type=semver`
tags on release.

### How should the image be pinned?

`compose.yml` builds from `uv.lock`, so it reproduces the exact locked commit;
`compose.ghcr.yml` pulls whatever `:main` is now. Two files, two answers. Inheriting `FROM
ghcr.io/dhis2/open-climate-service` was considered and rejected because a moving base tag would
defeat the lock — but that changes if upstream tags releases.

### Should credentials reach the running service?

`env_file` puts everything in `.env` into the container, including a CDS key if you keep one
there — visible to `docker inspect` and anyone who can exec in. The service does not need it:
`make populate` injects credentials for the duration of that command only. Convenient, but more
than least privilege for a public instance.

### Read-only is a config key, not a property

Until PR #329 lands, `read_only: true` does nothing, and even afterwards it is one key away
from being off. Mounting the data directory `:ro` and running behind an allowlist proxy would
make it structural instead. See [CLIM-864](https://dhis2.atlassian.net/browse/CLIM-864).

### Storage is hardcoded to the local filesystem

Every Icechunk repository is opened with `icechunk.local_filesystem_storage(...)` —
`ingestions/services.py:661`, `data_manager/services/downloader.py:247` and `:346`,
`data_accessor/services/accessor.py:137`, `streaming/store.py:31`, `stac/media_types.py:101` —
and there is no `s3_storage`, `gcs_storage` or `azure_storage` anywhere, nor any config key for
a bucket, endpoint or credentials. `get_data_dir()` returns a `Path`, so it cannot carry a URI
either.

The capability is present but unwired: icechunk 2.1.2 ships `s3_storage`, `gcs_storage`,
`azure_storage`, `r2_storage`, `tigris_storage` and `http_storage`, so RustFS or MinIO would
work through `s3_storage` with a custom endpoint. Reading is already more agnostic than writing
— `open_zarr_dataset` documents handling S3 and GCS URIs — but `open_icechunk_dataset` twelve
lines below calls `Path.exists()` and then `local_filesystem_storage`. Clients are not
affected: `/icechunk/` and `/zarr/` serve stores over HTTP.

This is why ingestion logs `The LocalFileSystem storage is not safe for concurrent commits`.
Benign here — one uvicorn process, ingestion serialised — but it becomes real with multiple
workers or concurrent ingestion, which is exactly when an object store is wanted and
unavailable. Object-store backing would also retire the absolute-path problem below, since
stores would live at a stable URI rather than a machine-specific path. Relevant to hosting,
[CLIM-857](https://dhis2.atlassian.net/browse/CLIM-857).

### The artifact registry could easily be portable, and is not

`records.json` stores resolved absolute paths, so a data directory is only servable at the path
it was ingested under — copy it anywhere else and the catalogue is silently empty.

This is a choice, not a storage constraint. Icechunk accepts relative paths for both create and
open; the absoluteness comes from `services.py:405` explicitly calling
`str(store_path.resolve())`. And the path is entirely derivable in the first place:
`get_icechunk_path` is `DOWNLOAD_DIR / f"{dataset_id}.icechunk"` (`downloader.py:221-224`),
with the prefix being just the dataset id. So the stored path is redundant with `data_dir` plus
`dataset_id`, and storing it is what breaks portability.

Recording it relative to `data_dir` — or deriving it and not recording it — would remove the
problem and make `make adopt-data` unnecessary. For a demo instance whose premise is "copy
stores in from elsewhere", this is the case that should work by default. Worth raising with
upstream.

### There is no CLI, so this repo reaches into internals

`climate-service` is the only entry point and it does nothing but start uvicorn — 20 lines, no
subcommands, no argument parsing, host and port from the environment. So `populate.py` and
`adopt_data.py` import `open_climate_service.ingestions.processes` and edit `records.json`
directly. Those are internals with no deprecation cycle, and this repo silently depends on
their shape. [CLIM-862](https://dhis2.atlassian.net/browse/CLIM-862) proposes a supported CLI;
if it lands, both scripts should collapse into calls to it. Until then, `make upgrade` can
break them without warning.

### Ports are configurable, but only carefully

`PORT` sets the host port for both `make run` and the compose files; the container always
listens on 8003 internally and the mapping targets that. The container's `PORT` is pinned in
`environment:` for exactly this reason — `env_file` would otherwise let a `PORT` in `.env` move
the listener off the port Docker forwards to, leaving the service unreachable and the
healthcheck failing, with nothing in the logs to suggest a port mismatch. Worth deciding
whether the internal port should be configurable at all, or fixed as it is now.

### What belongs in the demo set?

`populate.py` ingests five datasets; the ERA5-Land rows need CDS credentials and take roughly a
minute per year of monthly data, which makes `make populate` a slow first experience. A
credential-free subset would run in about two minutes.
