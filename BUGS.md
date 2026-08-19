# Upstream bugs

Defects in [open-climate-service](https://github.com/dhis2/open-climate-service) found while
deploying this instance. Nothing here is fixable in this repository. Each entry records how
it was reproduced, so it can be re-checked against a newer build.

Observed against image revisions `9ece4c3` and `e7f23f5` (2026-08-18/19), Nepal extent.

---

## 1. Extending an artifact writes the data, then fails, leaving the registry stale

**Severity: high.** The catalogue silently advertises less data than the store holds.

`execute_ingestion` for a range adjacent to an existing artifact fetches and commits the new
periods, and only then compares the store's total coverage against the requested scope. They
never match when extending, so it raises — after the write, and without updating the registry.

```
409: Materialized artifact coverage does not match the requested scope:
     coverage=2024-01-01..2024-02-21, request=2024-02-01..2024-02-21
```

`ingestions/services.py:399`.

Reproduction — ingest January, then February:

```bash
execute_ingestion(dataset_id='clms_gpp_dekadal', start='2024-01-01', end='2024-01-31')
execute_ingestion(dataset_id='clms_gpp_dekadal', start='2024-02-01', end='2024-02-29')  # 409
```

Afterwards the store and the API disagree:

| | |
| --- | --- |
| store, `0/gpp` | `(6, 1378, 2739)` -- 2024-01-01/11/21, 02-01/11/21 |
| `GET /datasets` | `2024-01-01 -> 2024-01-21` |

It compounds. A later ingest through `/manage` for 2025-08-19..2026-08-19 fetched every
dekad up to the availability limit and left:

| | |
| --- | --- |
| store | **39 dekads**, 2024-01-01 -> 2026-07-01, monotonic, 260 MB |
| `GET /datasets` | `2024-01-01 -> 2024-01-21` (3 dekads) |

92% of what was downloaded is unreachable, and nothing after the failed call says so. Seen
the same way on `chirps3_precipitation_daily` and `era5land_temperature_monthly`.

**Only the registry is wrong** -- the store is intact and correctly ordered. Editing the
record's `coverage.temporal` and `request_scope` to the store's real range, then restarting,
restores the whole series without re-downloading:

```python
r["coverage"]["temporal"] = {"start": "2024-01-01", "end": "2026-07-01"}
r["request_scope"] = {**r["request_scope"], "start": "2024-01-01", "end": "2026-07-01"}
```

Verified afterwards: `POST /result` over 2026-06 returns all three June dekads, gpp mean
9.502 g C m-2 day-1 against 2.135 in January -- the monsoon signal, so the late data is real
and was simply hidden.

Workaround: ingest the whole range in one call, or tick **Overwrite if already ingested**
(`overwrite=True`).

---

## 2. A failed ingest leaves a store that blocks every retry

**Severity: medium.** Recovery requires deleting a directory by hand.

When an ingest fails after creating the icechunk repository but before committing periods, the
next attempt refuses to start:

```
RuntimeError: Existing store at /app/data/downloads/<dataset>.icechunk is not empty,
              but committed periods could not be determined safely
```

`streaming/orchestrator.py:196`. The store is 12K, three files, no data. Every subsequent run
fails identically until it is removed:

```bash
rm -rf data/downloads/<dataset>.icechunk
```

Hit twice: once after the credentials error in bug 4, once after a plugin dependency was
missing. The first failure is recoverable; the state it leaves behind is not, without manual
intervention.

---

## 3. `POST /result` returns 500 for three advertised output formats

**Severity: medium.** `GET /file_formats` advertises nine output formats. Three of them crash.

| Format | Result |
| --- | --- |
| NETCDF, GTIFF, CSV | 200, valid payload |
| ZARR | 400, `Synchronous datacube results do not support ZARR output; use a non-ZARR format or submit a batch job` |
| **GEOJSON, PARQUET, JSON** | **500** |

```
IsADirectoryError: [Errno 21] Is a directory: '/tmp/tmpXXXXXXXX/result.zarr'
```

`openeo/routes.py:361` calls `path.read_bytes()` on a directory. ZARR is caught and refused
cleanly; these three fall through to the same code path and crash. They should either work or
return the 400 that ZARR gets.

Reproduction: any `load_collection` + `save_result` graph with `format: GEOJSON`.

---

## 4. A missing `plugins_dir` is a startup WARNING and a route-level 500

**Severity: medium.** The two disagree, and the healthcheck sides with the lenient one.

Startup, when `plugins_dir` does not exist:

```
WARNING open_climate_service - Instance plugins: plugins_dir '/app/plugins' does not exist
        or is not a directory - no instance plugins will load.
```

The service starts, reports healthy, and answers `/`, `/health`, `/info`, `/extent`,
`/datasets`, `/collections`, `/processes`, `/stac` and `/map` with 200. But:

```
GET /dataset-templates/  ->  500
ValueError: plugins_dir '/app/plugins' does not exist or is not a directory
```

`data_registry/services/datasets.py:111`. Either the directory is required -- in which case
startup should fail rather than warn -- or it is optional, in which case listing templates
should degrade to the built-ins.

---

## 5. `worldpop_population_change` cannot be ingested

**Severity: low.** A built-in template that no caller can use.

```
500: Dataset 'worldpop_population_change' does not define ingestion.plugin
```

It is listed by `GET /dataset-templates/` alongside templates that do work, with nothing to
distinguish it until ingestion is attempted.

---

## 6. Appending an earlier range leaves a non-monotonic time axis

**Severity: low**, but silent, and consumers assuming sorted time will misread the store.

Observed on `chirps3_precipitation_daily` after ingesting 2021-2025 into a store that already
held 2026-05:

```
first 3 : 2026-05-01, 2026-05-02, 2026-05-03
last 3  : 2025-12-29, 2025-12-30, 2025-12-31
monotonic increasing: False   (1 backward step)
min 2021-01-01  max 2026-05-31  duplicates: 0
```

Nothing is lost or duplicated -- the earlier block is simply appended after the later one.
The February extension in bug 1 stayed monotonic, so this appears specific to appending a
range that precedes existing data.

---

## 7. `units: people` warns on every startup

**Severity: cosmetic.** Three WARNING lines per boot, from upstream's own templates:

```
Dataset template 'worldpop_population_global2_R2025A_100m' in worldpop.yaml:
  units 'people' is not a recognised CF/udunits unit
```

Also `worldpop_agesex_global2_R2025A_100m` and `worldpop_population_change`. Either the unit
should be one udunits accepts, or population templates should be exempt from the check.
