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
The dependency tracks open-climate-service `main`, and read-only mode is still unmerged
there (PR #329). Config on `main` is read as a plain dict, so an unrecognised `read_only`
key is silently ignored rather than rejected: the service starts normally and serves every
write endpoint — ingestion, sync, stored process graphs, batch jobs and the `/manage`
console.

**Do not expose this instance publicly as it stands.** Until #329 lands it needs to stay
private, or sit behind a reverse proxy that allowlists the read paths — see Deployment
notes.

The key is kept in the config deliberately rather than deleted: it records the intended
posture, and it begins taking effect on its own once #329 merges, with nothing to change
here. What it will do then:

| | |
| --- | --- |
| **Open** | `/collections`, `/stac`, `/datasets`, `/processes`, `/process_graphs`, `/extent`, `/zarr/…`, `/icechunk/…`, the landing page, `/map`, and `POST /result` |
| **Refused (403)** | ingestion and sync, the `/manage` console, `PUT`/`DELETE /process_graphs/{id}`, and batch jobs |

`POST /result` stays open because it is how anyone actually *uses* the instance — it is a
POST only because the process graph travels in the request body, and it cannot publish a
dataset. Batch jobs are closed entirely rather than made read-only: there is no request
identity yet, so the job namespace would be shared between visitors.

Once read-only is in effect, `GET /info` reports it and the openEO capabilities document at
`GET /?f=json` omits the endpoints that would refuse, so clients discover the reduced
surface rather than finding it by failing.

> **Check this after every deploy, and after every `make upgrade`** — the pin tracks a
> moving branch. `make verify` reports the current state; it does not fail when the
> instance is writable, because on this pin that is the expected result.
>
> ```bash
> curl -s https://<host>/info | grep read_only   # absent today; `true` once #329 lands
> curl -s -o /dev/null -w '%{http_code}\n' -X POST https://<host>/ingestions -d '{}'
> #   422 today — the request is accepted and validated; 403 once read-only is in effect
> ```

## Running it

In a virtualenv:

```bash
cp .env.example .env      # set CLIMATE_SERVICE_CONFIG to an absolute path
make install
make run                  # http://127.0.0.1:8003
make verify               # report what the instance is actually serving
```

In Docker, building from this repo's pin:

```bash
make docker-up            # http://127.0.0.1:8003
make verify
make docker-down
```

Or from the image upstream publishes, without building:

```bash
make docker-up COMPOSE=compose.ghcr.yml
```

`COMPOSE=compose.ghcr.yml` works with every `docker-*` target. The two differ in what
they pin: `compose.yml` builds from `uv.lock`, so the container is the exact commit this
repo locked and a rebuild never moves on its own. `compose.ghcr.yml` pulls
`ghcr.io/dhis2/open-climate-service:main`, which tracks upstream's `main` branch and moves
when upstream does. Use the built image when you want the pin to hold; use the published
one to try the instance without a build. The published image is `linux/amd64` only, so it
runs emulated on arm64.

Both run as the `ocs` user (uid/gid 999) and keep ingested data in a named `data` volume.
`make docker-shell` gets you a shell inside for operator tasks.

## Ingesting data

Ingestion is an operator task performed on the host. The HTTP ingestion endpoints happen to
be reachable on the current pin, but the host-side call is still the supported path — it is
what lets read-only be absolute once it is in effect, with no exemption, token or trusted
header that could be misconfigured into a bypass.

ERA5-Land needs Copernicus Climate Data Store credentials in `~/.ecmwfdatastoresrc`;
CHIRPS3 and WorldPop are public.

```bash
uv run python -c "
from open_climate_service.ingestions.processes import execute_ingestion
execute_ingestion(dataset_id='era5land_temperature_monthly', start='2020-01', end='2024-12')
"
```

A supported CLI for this is [CLIM-862](https://dhis2.atlassian.net/browse/CLIM-862).

A representative demo set — enough that the catalogue isn't empty, small enough to stay
cheap:

| Dataset | Suggested range |
| ------- | --------------- |
| `era5land_temperature_monthly` | 2020-01 → 2024-12 |
| `era5land_precipitation_monthly` | 2020-01 → 2024-12 |
| `chirps3_precipitation_daily` | a recent month |
| `worldpop_population_global2_R2025A_100m` | 2020 → 2025 |
| `era5land_temperature_monthly_normal_1991_2020` | the normal is its own dataset |

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
