"""Contract checks for this instance's dataset plugin.

A plugin class is imported **lazily, at ingest time** — the API starts, the dataset still
lists in `/collections`, and a breakage only surfaces when someone runs that ingest. This
instance tracks `open-climate-service` at git **main** (see pyproject.toml), so it is more
exposed than a pinned instance: a core change can break the plugin between one `make upgrade`
and the next, with nothing to catch it.

Nothing here touches the network or needs credentials.
"""

from __future__ import annotations

import importlib
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from open_climate_service.shared.time import dekad_bounds, dekad_period_ids
from open_climate_service.streaming import BaseDatasetPlugin

_DATASETS_DIR = Path(__file__).resolve().parent.parent / "plugins" / "datasets"


def _templates() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(_DATASETS_DIR.glob("*.yaml")):
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        out.extend(t for t in (loaded if isinstance(loaded, list) else [loaded]) if isinstance(t, dict))
    return out


_TEMPLATES = _templates()


def test_templates_are_present() -> None:
    """Guard the guard: if this collapses to nothing, the tests below vacuously pass."""
    assert _TEMPLATES, f"no dataset templates found under {_DATASETS_DIR}"


@pytest.mark.parametrize("template", _TEMPLATES, ids=lambda t: str(t.get("id")))
class TestDeclaredPlugin:
    def test_plugin_imports_and_satisfies_the_contract(self, template: dict[str, Any]) -> None:
        path = (template.get("ingestion") or {}).get("plugin")
        assert isinstance(path, str) and path, f"{template.get('id')} declares no ingestion.plugin"
        module_name, _, class_name = path.rpartition(".")
        cls = getattr(importlib.import_module(module_name), class_name)
        assert issubclass(cls, BaseDatasetPlugin), f"{path} is not a BaseDatasetPlugin"
        instance = cls()
        assert callable(instance.periods)
        assert callable(instance.fetch_period)


def test_gpp_declares_a_dekadal_cadence() -> None:
    """A dekad is 8 to 11 days, so no ISO duration describes the cadence.

    Open Climate Service publishes a null STAC step for an irregular cadence, so a declared
    `resolution` would either be ignored or wrongly imply regular spacing.
    """
    gpp = next(t for t in _TEMPLATES if t["id"] == "clms_gpp_dekadal")
    assert gpp["period_type"] == "dekadal"
    assert "resolution" not in (gpp.get("extents", {}).get("temporal") or {}), (
        "an ISO resolution on an irregular cadence is ignored downstream; do not declare one"
    )


def test_dekad_window_does_not_spill_into_the_next_month() -> None:
    """Why the plugin uses `dekad_bounds` rather than a fixed 10-day window.

    A third dekad ends with its month, so `start + 9 days` overshoots a short one. For
    2025-02-21 it lands on 2025-03-02, and a STAC search over that range matches two items —
    February's dekad and March's — so the wrong raster can be selected for the period.
    """
    start = "2025-02-21"
    naive_end = date.fromisoformat(start) + timedelta(days=9)
    real_start, real_end = dekad_bounds(start)

    assert naive_end.month == 3, "precondition: the naive window crosses the month boundary"
    assert real_end == date(2025, 2, 28)
    assert real_start == date(2025, 2, 21)
    # 8 days in a common-year February, against the 10 a fixed window assumes.
    assert (real_end - real_start).days + 1 == 8


def test_periods_snap_to_whole_dekads() -> None:
    """A partially covered dekad is included: it is the smallest unit the data has."""
    ids = dekad_period_ids("2025-01-05", "2025-03-02")
    assert ids[0] == "2025-01-01", "the dekad containing the start must be included whole"
    assert ids == [
        "2025-01-01",
        "2025-01-11",
        "2025-01-21",
        "2025-02-01",
        "2025-02-11",
        "2025-02-21",
        "2025-03-01",
    ]


def test_periods_are_clamped_by_availability() -> None:
    """`cutoff` is how a request past the latest publication returns nothing, not an error."""
    assert dekad_period_ids("2030-01-01", "2030-12-31", cutoff="2026-07-01") == []
