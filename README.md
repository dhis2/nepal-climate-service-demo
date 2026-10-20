# Nepal Climate Service — public demo instance

A publicly reachable [Open Climate Service](https://github.com/dhis2/open-climate-service)
instance configured to the Nepal extent, kept online as a stable demo endpoint:

**<https://ocs-demo-nepal.dhis2.org/>**

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

## Connecting

| Client | URL |
| --- | --- |
| Browser, API overview | <https://ocs-demo-nepal.dhis2.org/> |
| Map viewer | <https://ocs-demo-nepal.dhis2.org/map> |
| API docs | <https://ocs-demo-nepal.dhis2.org/docs> |
| STAC catalogue (STAC Browser, QGIS, pystac) | <https://ocs-demo-nepal.dhis2.org/stac> |
| openEO (Python client, Web Editor) | `https://ocs-demo-nepal.dhis2.org` |
| GeoLibre plugin | `https://ocs-demo-nepal.dhis2.org` as the service URL |
| Datasets and feature collections | `/datasets`, `/collections`, `/features` |
| Zarr stores (zarr-layer, xarray) | `/zarr/{dataset_id}` |

```python
import openeo
connection = openeo.connect("https://ocs-demo-nepal.dhis2.org")
```

## What it serves

| Dataset | Coverage |
| --- | --- |
| `chirps3_precipitation_monthly` | 1990-01 onwards |
| `era5land_temperature_monthly` | 1990-01 onwards |
| `chirps3_precipitation_monthly_normal_1991_2020`, `era5land_temperature_monthly_normal_1991_2020` | 1991–2020 monthly normals |
| `chirps3_precipitation_monthly_anomaly_1991_2020`, `chirps3_precipitation_monthly_relative_anomaly_1991_2020`, `era5land_temperature_monthly_anomaly_1991_2020` | the current year, against the normals |
| `worldpop_population_global2_100m` | 2015–2030 |
| `nepal_country`, `nepal_provinces`, `nepal_districts` | Overture Maps boundaries, see below |

The monthly datasets are kept current by scheduled sync (see [Ingesting data](#ingesting-data)).
`GET /data-sources` lists everything this instance could ingest, with parameters.

## Almost entirely stock Open Climate Service

Everything here is built in **except one dataset plugin and one boundary template**, so what
you see is close to what a stock install does, with very little instance-specific code to keep
working as the core service moves.

The exception is `plugins/rasters/clms_gpp.py` — CLMS Gross Primary Production. It
demonstrates two things no built-in does: a **dekadal** cadence, where the third dekad of a
month is 8 to 11 days long and the STAC step is therefore null rather than a duration, and a
**credentialed S3 source** read with GDAL range requests. Both are patterns instance authors
ask about, and a demo showing only the easy cases does not answer them.

`plugins/vectors/overture_nepal.yaml` adds Nepal's first three administrative levels from
[Overture Maps](https://docs.overturemaps.org/guides/divisions/) divisions, one feature
collection each: `nepal_country` (1 feature), `nepal_provinces` (7) and `nepal_districts`
(77). It configures the built-in `overture` provider and needs no credentials. The data is
ODbL-1.0: © OpenStreetMap contributors, © Overture Maps Foundation.

The built-in data sources cover ERA5-Land (temperature and precipitation, daily, monthly and
daily-from-hourly), ERA5-HEAT UTCI, CHIRPS3 (daily and monthly), WorldPop (total population
and population change), Copernicus DEM, and 1991–2020 normals and anomalies for ERA5-Land and
CHIRPS3.

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
> writable instance:
>
> ```bash
> make verify BASE=https://ocs-demo-nepal.dhis2.org
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

To update a deployment to the current upstream build:

```bash
git pull
docker compose build --pull
docker compose up -d
make verify BASE=https://ocs-demo-nepal.dhis2.org
```

## Ingesting data

Read-only applies to HTTP, so ingestion is an operator task, not something a visitor can
trigger. This is what lets the switch be absolute: there is no exemption, token or trusted
header that could be misconfigured into a bypass.

Ingest **through a container on the deploy host**, writing to the same data directory the
public container serves. The artifact registry records absolute paths, so a store ingested
anywhere else is recorded at a path the container cannot resolve and is dropped at startup as
a stale artifact. A published store appears on the public instance without a restart.

ERA5-Land needs Copernicus Climate Data Store credentials; CHIRPS3, WorldPop and the Overture
boundaries are public. CLMS GPP needs Copernicus Data Space Ecosystem S3 keys
([register](https://dataspace.copernicus.eu/), then
[generate keys](https://eodata-s3keysmanager.dataspace.copernicus.eu/)):

```bash
ECMWF_DATASTORES_URL=https://cds.climate.copernicus.eu/api
ECMWF_DATASTORES_KEY=<KEY>
CDSE_S3_ACCESS_KEY=<ACCESS-KEY>
CDSE_S3_SECRET_KEY=<SECRET-KEY>
```

**Keep these out of `.env` on the deploy host.** Compose reads `.env` automatically and
`compose.yml` passes the credentials into the public container. Put them in a separate,
owner-only file (for example `worker.env`) that only the ingesting container reads.

### Private writable worker

The hosted demo runs a second Compose project next to the public one: the same image and
data directory, with `read_only: false`, the scheduler enabled, the credentials from
`worker.env`, and a port bound to `127.0.0.1` only. It is not routed by the reverse proxy,
so it is reachable only through an SSH tunnel:

```bash
ssh -N -L 8013:127.0.0.1:8013 <deploy-host>
# then http://localhost:8013/manage, or the API at http://localhost:8013
```

Its config is `climate-service.yaml` with two changes:

```yaml
read_only: false
scheduler:
  enabled: true
```

The worker is the only process that runs sync schedules; Open Climate Service allows exactly
one scheduling process per data directory. Create the schedules from each dataset's
**Schedule** tab in `/manage`, or with `POST /schedules/sync`. After rebuilding the public
image, run `docker compose up -d` in the worker's project too, so both run the same build.

### Throwaway container

For a one-off ingest without a long-running writable process:

```bash
set -a; . ./worker.env; set +a
docker compose run --rm --no-deps \
  -e CDSE_S3_ACCESS_KEY -e CDSE_S3_SECRET_KEY \
  -e ECMWF_DATASTORES_URL -e ECMWF_DATASTORES_KEY \
  api python -c "
from open_climate_service.ingestions.processes import execute_ingestion
execute_ingestion(dataset_id='era5land_temperature_monthly', start='1990-01', end='2026-09')
"
```

**Ingest a whole range in one call, or tick "Overwrite if already ingested".** Extending an
existing dataset with a second, adjacent ingestion writes the new periods and then fails the
coverage check, leaving the registry pointing at the old range -- the data is in the store
but the catalogue does not advertise it, and nothing after the failure says so. Scheduled
sync is the supported way to extend a dataset.

A supported CLI for ingestion is [CLIM-862](https://dhis2.atlassian.net/browse/CLIM-862).

## Deployment notes

- **Hosting.** The demo runs on an NREC VM behind a Traefik reverse proxy, which terminates
  HTTPS. A host-specific `compose.override.yml` routes the public container through Traefik
  without publishing a port, sets `CLIMATE_SERVICE_BASE_URL`, and mounts the data
  directory from a separate data volume. Provisioning is
  [CLIM-857](https://dhis2.atlassian.net/browse/CLIM-857).
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
