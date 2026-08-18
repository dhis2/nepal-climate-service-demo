"""CLMS Gross Primary Production (GPP) — 300 m, dekadal, from the Copernicus Land Monitoring Service.

Published on the 1st, 11th and 21st of each month from 2014 onwards, as global Cloud-Optimised
GeoTIFFs on the Copernicus Data Space Ecosystem's S3 storage. Only the tiles covering the
instance bbox are read, via GDAL range requests.

Credentials are required. Register at https://dataspace.copernicus.eu/ and generate S3 keys at
https://eodata-s3keysmanager.dataspace.copernicus.eu/, then supply them either way round:

    CDSE_S3_ACCESS_KEY=<ACCESS-KEY>        # environment, checked first
    CDSE_S3_SECRET_KEY=<SECRET-KEY>

    # or ~/.aws/credentials
    [cdse]
    aws_access_key_id = <ACCESS-KEY>
    aws_secret_access_key = <SECRET-KEY>

`CDSE_S3_PROFILE` picks a different profile name, `CDSE_S3_ENDPOINT` a different S3 host.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

import numpy as np
import xarray as xr
from open_climate_service.shared.time import dekad_bounds, dekad_period_ids
from open_climate_service.streaming import BaseDatasetPlugin

logger = logging.getLogger(__name__)

_COLLECTION = "clms_gpp_global_300m_10daily_v2_cog"
_ASSET_KEY = "gpp300_gpp"
_STAC_URL = "https://catalogue.dataspace.copernicus.eu/stac"
_S3_BUCKET = "eodata"
_VARIABLE = "gpp"
_FIRST_DEKAD = "2014-01-01"

# CDSE's general S3 host. Keys issued against the OTC (Amsterdam) backend can answer
# InvalidAccessKeyId here; `https://eodata.ams.dataspace.copernicus.eu` is the alternative.
_DEFAULT_S3_ENDPOINT = "https://eodata.dataspace.copernicus.eu"
_DEFAULT_PROFILE = "cdse"

# STAC page size. `items()` pages lazily and every page is an HTTP request, so a small page
# size turns one logical search into many calls and trips CDSE's WAF rate limit. At 100, a
# year of dekads resolves in three requests.
_STAC_PAGE_SIZE = 100

# Quality flags, stored in the raster's negative range and masked before the CF scale/offset is
# applied. Only these two values are dropped rather than everything below zero: GPP is
# non-negative, but keeping the mask specific means the same code is correct if it is ever
# pointed at NPP, which genuinely can be negative.
_FLAG_MISSING = -1
_FLAG_WATER = -2


def _consolidation_level(item: Any) -> int:
    """The item's RT (real-time) consolidation level, higher being more consolidated."""
    match = re.search(r"-RT(\d+)_", str(getattr(item, "id", "")))
    return int(match.group(1)) if match else -1


def _best_item(items: list[Any]) -> Any | None:
    """The most consolidated item of a dekad, or None when there are none.

    CDSE publishes four items per dekad — RT0, RT1, RT2 and RT6 — with the same datetime and
    increasing amounts of input data behind them. Picking by highest RT keeps the choice
    deterministic; taking whichever the API lists first would mix preliminary and consolidated
    data from one dekad to the next.
    """
    return max(items, key=_consolidation_level) if items else None


def _cdse_credentials() -> tuple[str, str]:
    """Resolve CDSE S3 keys from the environment, else from a boto3 profile.

    A deployed instance sets the keys in its environment, which needs no home directory or
    files; an operator's machine more often keeps them in `~/.aws/credentials`. Environment
    first, so a deployment cannot be silently overridden by a stray local profile.
    """
    import os

    access_key = os.environ.get("CDSE_S3_ACCESS_KEY")
    secret_key = os.environ.get("CDSE_S3_SECRET_KEY")
    if access_key and secret_key:
        return access_key, secret_key

    profile = os.environ.get("CDSE_S3_PROFILE", _DEFAULT_PROFILE)
    try:
        import boto3

        credentials = boto3.Session(profile_name=profile).get_credentials()
        if credentials is not None:
            frozen = credentials.get_frozen_credentials()
            if frozen.access_key and frozen.secret_key:
                logger.info("Using CDSE credentials from boto3 profile %r", profile)
                return frozen.access_key, frozen.secret_key
    except Exception as exc:  # noqa: BLE001 — a missing profile is one of several boto3 errors
        logger.debug("boto3 profile %r unusable: %s", profile, exc)

    raise RuntimeError(
        "CLMS GPP needs CDSE S3 credentials. Either set CDSE_S3_ACCESS_KEY and "
        f"CDSE_S3_SECRET_KEY, or add a [{profile}] profile with aws_access_key_id and "
        "aws_secret_access_key to ~/.aws/credentials. Keys are generated at "
        "https://eodata-s3keysmanager.dataspace.copernicus.eu/"
    )


def _search_stac(**query: Any) -> list[Any]:
    """Run a STAC item search, retrying with backoff on CDSE's WAF 429.

    The catalogue sits behind a WAF that rate-limits bursts, and the 429 surfaces while lazily
    iterating `search.items()` rather than at call time — so the retry has to wrap the
    iteration. A retry restarts pagination, which is why the page size matters: fewer pages
    means less to redo.
    """
    import random
    import time

    import pystac_client
    from pystac_client.exceptions import APIError

    delay = 2.0
    for attempt in range(6):
        try:
            return list(pystac_client.Client.open(_STAC_URL).search(**query).items())
        except APIError as exc:
            message = str(exc)
            if "429" not in message and "Rate limit" not in message:
                raise
            if attempt == 5:
                raise
            pause = delay + random.uniform(0.0, 1.0)
            logger.warning("CDSE STAC rate-limited (429); retrying in %.1fs", pause)
            time.sleep(pause)
            delay = min(delay * 2, 60.0)
    return []


class ClmsGppPlugin(BaseDatasetPlugin):
    """Dekadal CLMS GPP from CDSE, one committed timestep per dekad."""

    max_concurrency = 2
    commit_batch_size = 1
    rechunk_time = 30
    pyramid: bool = True

    def __init__(self, **params: Any) -> None:
        super().__init__(**params)
        # date -> STAC item, filled by periods(). Held on the instance because the orchestrator
        # calls periods() once and then fetch_period() per dekad on the same object.
        self._items_by_date: dict[str, Any] = {}

    async def periods(self, start: str, end: str) -> list[str]:
        import asyncio

        latest = await asyncio.to_thread(self._latest_published_dekad)
        if latest is None:
            logger.warning("CLMS collection %s published no items; nothing to ingest", _COLLECTION)
            return []
        # `cutoff` clamps to what the source actually has, so a request running past the latest
        # publication asks for nothing rather than failing per missing dekad.
        ids = dekad_period_ids(max(start[:10], _FIRST_DEKAD), end[:10], cutoff=latest)
        if ids:
            # One search for the whole span. Searching per dekad in fetch_period would be ~37
            # searches for a year, two at a time, which trips the WAF rate limit.
            await asyncio.to_thread(self._cache_items, ids[0], ids[-1])
        return ids

    def _latest_published_dekad(self) -> str | None:
        """The date of the most recently published dekad, or None if the collection is empty."""
        items = _search_stac(collections=[_COLLECTION], max_items=1, sortby="-datetime", limit=1)
        return items[0].datetime.date().isoformat() if items else None

    def _cache_items(self, start: str, end: str) -> None:
        """Resolve each dekad's most consolidated STAC item in one search, keyed by date."""
        items = _search_stac(
            collections=[_COLLECTION],
            datetime=f"{start}T00:00:00Z/{end}T23:59:59Z",
            limit=_STAC_PAGE_SIZE,
        )
        grouped: dict[str, list[Any]] = {}
        for item in items:
            grouped.setdefault(item.datetime.date().isoformat(), []).append(item)
        self._items_by_date = {date_: best for date_, group in grouped.items() if (best := _best_item(group))}
        logger.info(
            "Resolved %d CLMS GPP dekads from %d STAC items for %s..%s",
            len(self._items_by_date),
            len(items),
            start,
            end,
        )

    async def fetch_period(self, period_id: str, bbox: list[float], **_: Any) -> xr.Dataset:
        import asyncio

        return await asyncio.to_thread(self._fetch, period_id, bbox)

    def _fetch(self, period_id: str, bbox: list[float]) -> xr.Dataset:
        import os

        import rasterio
        import rioxarray as rxr
        from rasterio.session import AWSSession

        access_key, secret_key = _cdse_credentials()
        endpoint = os.environ.get("CDSE_S3_ENDPOINT", _DEFAULT_S3_ENDPOINT)

        xmin, ymin, xmax, ymax = map(float, bbox)
        # The dekad's true extent: a third dekad runs to the end of its month, so it is 8 to 11
        # days long and a fixed 10-day window would fall short or overrun into the next dekad.
        first_day, last_day = dekad_bounds(period_id)

        item = self._items_by_date.get(period_id)
        if item is None:
            # periods() was bypassed — a resume with a pre-supplied period list. Costs one search.
            item = _best_item(
                _search_stac(
                    collections=[_COLLECTION],
                    bbox=[xmin, ymin, xmax, ymax],
                    datetime=f"{first_day.isoformat()}T00:00:00Z/{last_day.isoformat()}T23:59:59Z",
                    limit=_STAC_PAGE_SIZE,
                )
            )
            if item is None:
                raise ValueError(f"No CLMS GPP item published for the dekad starting {period_id}")

        s3_key = item.assets[_ASSET_KEY].href.removeprefix(f"s3://{_S3_BUCKET}/")
        logger.info(
            "Fetching CLMS GPP %s (RT%d) from s3://%s/%s",
            period_id,
            _consolidation_level(item),
            _S3_BUCKET,
            s3_key,
        )

        # rasterio refuses AWS options passed to Env directly ("handled exclusively by boto3"),
        # so the keys go in through AWSSession. Env then scopes the whole lot thread-locally,
        # which matters because max_concurrency runs fetches in parallel and process-wide env
        # mutation would race between them. AWS_VIRTUAL_HOSTING=FALSE selects path-style
        # addressing, which CDSE requires.
        session = AWSSession(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint,
            region_name="default",
        )
        with rasterio.Env(
            session,
            AWS_VIRTUAL_HOSTING="FALSE",
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
            CPL_VSIL_CURL_CHUNK_SIZE="1048576",
        ):
            da = rxr.open_rasterio(f"/vsis3/{_S3_BUCKET}/{s3_key}", chunks=None, masked=True, lock=False)
            if not isinstance(da, xr.DataArray):
                raise TypeError(f"Expected a DataArray from the CLMS raster, got {type(da).__name__}")
            da = da.rio.clip_box(minx=xmin, miny=ymin, maxx=xmax, maxy=ymax).squeeze("band", drop=True)
            da = da.where((da != _FLAG_MISSING) & (da != _FLAG_WATER))
            scale = float(da.attrs.get("scale_factor", da.encoding.get("scale_factor", 1.0)))
            offset = float(da.attrs.get("add_offset", da.encoding.get("add_offset", 0.0)))
            da = (da * scale + offset).astype("float32")
            # Materialise the range reads while the GDAL environment is still active.
            da = da.load()

        ds = da.to_dataset(name=_VARIABLE)
        ds = ds.expand_dims({"t": [np.datetime64(date.fromisoformat(period_id), "D")]})
        # A scalar `crs` coord (value 0) rides along on these COGs; the orchestrator infers the
        # grid and CRS from the data itself, so it is only clutter in the store.
        return ds.drop_vars("crs", errors="ignore")
