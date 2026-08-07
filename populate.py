"""Ingest the demo dataset set into a running instance.

Piped into the container by `make populate`; see "Ingesting data" in README.md.
The extent and bbox come from climate-service.yaml, so nothing here is Nepal-specific.
"""

from __future__ import annotations

import os
import sys
import time

from open_climate_service.ingestions.processes import execute_ingestion

# (dataset_id, start, end) -- the table in README.md. A range of None means the
# dataset defines its own period, as the 1991-2020 normals do.
DATASETS: list[tuple[str, str | None, str | None]] = [
    # Daily period type, so full dates -- a single recent month keeps this cheap.
    ("chirps3_precipitation_daily", os.getenv("CHIRPS_START", "2026-05-01"), os.getenv("CHIRPS_END", "2026-05-31")),
    ("worldpop_population_global2_R2025A_100m", "2020", "2025"),
    ("era5land_temperature_monthly", os.getenv("ERA5_START", "2020-01"), os.getenv("ERA5_END", "2024-12")),
    ("era5land_precipitation_monthly", os.getenv("ERA5_START", "2020-01"), os.getenv("ERA5_END", "2024-12")),
    ("era5land_temperature_monthly_normal_1991_2020", None, None),
]

# ERA5-Land pulls from the Copernicus CDS and needs credentials; the others are public.
NEEDS_CREDENTIALS = "era5land"


def main() -> int:
    only = sys.argv[1:]
    datasets = [d for d in DATASETS if not only or d[0] in only]
    if only and not datasets:
        print(f"no dataset matched {only}", file=sys.stderr)
        return 2

    have_credentials = bool(os.getenv("ECMWF_DATASTORES_KEY"))
    failed: list[str] = []

    for dataset_id, start, end in datasets:
        span = f"{start} -> {end}" if start else "own period"
        if NEEDS_CREDENTIALS in dataset_id and not have_credentials:
            print(f"SKIP  {dataset_id} ({span}) -- no CDS credentials")
            continue

        print(f"START {dataset_id} ({span})", flush=True)
        began = time.monotonic()
        try:
            execute_ingestion(dataset_id=dataset_id, start=start, end=end)
        except Exception as exc:  # keep going; one bad dataset should not stop the rest
            failed.append(dataset_id)
            print(f"FAIL  {dataset_id}: {type(exc).__name__}: {exc}", flush=True)
        else:
            print(f"OK    {dataset_id} in {time.monotonic() - began:.0f}s", flush=True)

    if failed:
        print(f"\n{len(failed)} of {len(datasets)} failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    print(f"\n{len(datasets)} ingested")
    return 0


if __name__ == "__main__":
    code = main()
    # Ingestion leaves dask worker threads behind that write to already-closed streams
    # during interpreter shutdown, filling the output with "Error in sys.excepthook"
    # after the run has already succeeded. Everything is committed by this point, so
    # leave without running finalisers.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
