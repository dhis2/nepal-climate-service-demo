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

## Almost entirely stock Open Climate Service

Everything here is built in **except one dataset plugin**, so what you see is close to what a
stock install does, with very little instance-specific code to keep working as the core
service moves.

The exception is `plugins/datasets/clms_gpp.py` — CLMS Gross Primary Production. It
demonstrates two things no built-in does: a **dekadal** cadence, where the third dekad of a
month is 8 to 11 days long and the STAC step is therefore null rather than a duration, and a
**credentialed S3 source** read with GDAL range requests. Both are patterns instance authors
ask about, and a demo showing only the easy cases does not answer them.

Available from the built-in templates:

| Source | Datasets |
| ------ | -------- |
| ERA5-Land | 2m temperature and precipitation — daily, monthly, and local-time-from-hourly variants |
| CHIRPS3 | Daily precipitation |
| WorldPop | Total population, population by age and sex, population change |
| Normals | 1991–2020 daily and monthly climatological normals for ERA5-Land and CHIRPS3 |

`GET /dataset-templates/` lists them all with their parameters.

## Read-only

`climate-service.yaml` sets `read_only: true`. Visitors can browse and compute; nobody can
change anything.

| | |
| --- | --- |
| **Open** | `/collections`, `/stac`, `/datasets`, `/processes`, `/process_graphs`, `/extent`, `/zarr/…`, `/icechunk/…`, the landing page, `/map`, and `POST /result` |
| **Refused (403)** | ingestion and sync, the `/manage` console, `PUT`/`DELETE /process_graphs/{id}`, and batch jobs |

`POST /result` stays open because it is how anyone actually *uses* the instance — it is a
POST only because the process graph travels in the request body, and it cannot publish a
dataset. Batch jobs are closed entirely rather than made read-only: there is no request
identity yet, so the job namespace would be shared between visitors.

`GET /info` reports `read_only`, and the openEO capabilities document at `GET /?f=json`
omits the endpoints that would refuse, so clients discover the reduced surface rather than
finding it by failing.

> **Check this after every deploy.** `read_only` is an ordinary config key, so a build of
> open-climate-service that predates read-only mode ignores it silently and serves a fully
> writable instance. `make verify` asserts it, or:
>
> ```bash
> curl -s https://<host>/info | grep read_only          # must be true
> curl -s -o /dev/null -w '%{http_code}\n' -X POST https://<host>/ingestions -d '{}'   # must be 403
> ```

## Running it

Docker is the only supported way to run this instance. The image is built on
`ghcr.io/dhis2/open-climate-service`, so the service and its dependencies come from
upstream's published build; this repository adds the config, the plugins and their
dependencies.

```bash
make docker-run           # http://127.0.0.1:8003, foreground
make verify               # confirm it is up and read-only
```

No `.env` is needed to serve. `PORT` selects the published host port, and
`CLIMATE_SERVICE_BASE_URL` sets the public URL behind a reverse proxy.

`climate-service.yaml`, `plugins/` and `./data` are bind-mounted from the host, so the
first two can be edited without a rebuild. Anything `climate-service.yaml` points at must
also be mounted, or the container will not find it.

`make test` runs the plugin contract checks inside the same image.

## Ingesting data

Read-only applies to HTTP, so ingestion is an operator task performed on the host. This is
what lets the switch be absolute: there is no exemption, token or trusted header that could
be misconfigured into a bypass.

ERA5-Land needs Copernicus Climate Data Store credentials in `~/.ecmwfdatastoresrc`;
CHIRPS3 and WorldPop are public. CLMS GPP needs Copernicus Data Space Ecosystem S3 keys
([register](https://dataspace.copernicus.eu/), then
[generate keys](https://eodata-s3keysmanager.dataspace.copernicus.eu/)), from either the
environment or an `~/.aws/credentials` profile:

```bash
CDSE_S3_ACCESS_KEY=<ACCESS-KEY>     # checked first
CDSE_S3_SECRET_KEY=<SECRET-KEY>
```

```ini
# ~/.aws/credentials
[cdse]
aws_access_key_id = <ACCESS-KEY>
aws_secret_access_key = <SECRET-KEY>
```

`compose.yml` passes the ingestion credentials in from `.env`, so `/manage` can ingest on
an instance running with `read_only: false`. They are empty unless set, so a host without
a `.env` gives the container none -- **keep `.env` off the deploy host**, where `read_only`
makes them unusable anyway and their only effect is to sit in the process environment.

To ingest without giving them to the running service at all, use a throwaway container:

```bash
set -a; . ./.env; set +a
docker compose run --rm --no-deps \
  -e CDSE_S3_ACCESS_KEY -e CDSE_S3_SECRET_KEY \
  -e ECMWF_DATASTORES_URL -e ECMWF_DATASTORES_KEY \
  api python -c "
from open_climate_service.ingestions.processes import execute_ingestion
execute_ingestion(dataset_id='era5land_temperature_monthly', start='2020-01', end='2024-12')
"
```

Stores are written to `./data` on the host, which the serving container mounts. Paths are
recorded as the container sees them, so ingest through the container rather than copying a
store in from elsewhere.

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

- **Pin the image.** The Dockerfile tracks `ghcr.io/dhis2/open-climate-service:main`, and
  that tag moves — upstream rebuilds it on every merge, so a rebuild can change the service
  under you. Pin a digest for anything long-lived. `main` is the only tag upstream
  publishes; switch to a release tag once one exists.
- **Set `CLIMATE_SERVICE_BASE_URL`** to the public HTTPS URL, or STAC and openEO links will
  point at the internal host.
- **CORS** is already permissive on the data and STAC routes, which is what browser clients
  (GeoLibre, STAC Browser, the openEO editor) need cross-origin.
- **Read-only protects integrity, not availability.** `POST /result` is still an unbounded
  compute endpoint. A public deployment should sit behind a reverse proxy that allowlists
  the open routes — an allowlist, not a denylist, so routes added in a later release aren't
  permitted by default — and applies request timeouts, body-size limits and per-IP rate
  limiting. Tracked as [CLIM-864](https://dhis2.atlassian.net/browse/CLIM-864).
- Restricting execution to specific workflows is [CLIM-863](https://dhis2.atlassian.net/browse/CLIM-863).

Hosting and provisioning is [CLIM-857](https://dhis2.atlassian.net/browse/CLIM-857).
