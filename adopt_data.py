"""Repoint artifact records at the data directory they are currently in.

The registry stores resolved absolute paths, so stores produced elsewhere -- in a
container, on another host -- are invisible once copied in under a different path, and
the catalogue comes up empty. Run this after copying data in; see "Where the data lives"
in README.md.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PATH_FIELDS = ("path", "asset_paths")
# Every store the service records lives under <data_dir>/downloads/: both the ingestion
# path (downloader.get_icechunk_path) and the openEO publish path (jobs.py) build
# DOWNLOAD_DIR / f"{dataset_id}.icechunk". That segment is what identifies the data
# directory a record was written under.
STORE_DIR = "downloads"


def anchor_path(entry: dict) -> str | None:
    """Return a recorded path to derive this entry's old data directory from.

    `path` is optional in the upstream schema (schemas.py:109) and readers fall back to
    `asset_paths[0]` (services.py:652), so a record with `path: null` is a real, servable
    record -- skipping it would leave its asset paths stale and drop it silently from the
    catalogue at the next exists() check.
    """
    value = entry.get("path")
    if isinstance(value, str) and value:
        return value
    assets = entry.get("asset_paths")
    if isinstance(assets, list):
        for asset in assets:
            if isinstance(asset, str) and asset:
                return asset
    return None


def old_data_dir(anchor: str) -> str | None:
    """Return the data directory `anchor` was written under, or None if unrecognised.

    Located by finding the 'downloads' segment rather than by counting parents up from
    the store: a record laid out any other way -- nested deeper, or not under a data
    directory at all -- would otherwise be rewritten against a root that is not its own,
    silently losing or duplicating path segments.
    """
    parts = Path(anchor).parts
    for index in range(len(parts) - 1, 0, -1):
        if parts[index] == STORE_DIR:
            return str(Path(*parts[:index]))
    return None


def repoint_entries(entries: list[dict], data_dir: Path) -> tuple[int, list[str]]:
    """Rewrite every recorded path onto data_dir. Returns (paths changed, warnings)."""
    changed = 0
    warnings: list[str] = []

    def repoint(value: str, old_root: str) -> str:
        """Swap the data directory, keeping the path below it intact."""
        nonlocal changed
        try:
            below = Path(value).relative_to(old_root)
        except ValueError:
            return value  # outside the old data directory -- not ours to move
        new = str(data_dir / below)
        if new != value:
            changed += 1
        return new

    for entry in entries:
        anchor = anchor_path(entry)
        if anchor is None:
            continue  # nothing recorded to repoint
        old_root = old_data_dir(anchor)
        if old_root is None:
            name = entry.get("dataset_id") or entry.get("artifact_id") or "?"
            warnings.append(f"{name}: {anchor} is not under a '{STORE_DIR}' directory -- left untouched")
            continue

        for field in PATH_FIELDS:
            value = entry.get(field)
            if isinstance(value, str):
                entry[field] = repoint(value, old_root)
            elif isinstance(value, list):
                entry[field] = [repoint(v, old_root) if isinstance(v, str) else v for v in value]

    return changed, warnings


def write_atomically(target: Path, payload: str) -> None:
    """Replace target in one step, so a reader never sees a partial file.

    The service reloads the registry whenever its mtime changes, so writing in place --
    which truncates first -- can be read back empty or half-written by a live instance.
    """
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(payload)
        # A fresh file gets umask defaults; keep whatever the registry had, so a
        # group-writable one stays writable for the service.
        os.chmod(tmp, target.stat().st_mode & 0o777)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)


def main() -> int:
    data_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "data").resolve()
    records = data_dir / "artifacts" / "records.json"
    if not records.exists():
        print(f"no records at {records}", file=sys.stderr)
        return 1

    entries = json.loads(records.read_text())
    changed, warnings = repoint_entries(entries, data_dir)

    if changed:
        # Redo the work against the file as it is now: a concurrent ingestion may have
        # appended a record since the first read, and writing the list read back then
        # would drop it. This leaves only the microseconds before os.replace.
        entries = json.loads(records.read_text())
        changed, warnings = repoint_entries(entries, data_dir)

    if changed:
        write_atomically(records, json.dumps(entries, indent=2))
        print(f"repointed {changed} paths in {len(entries)} records at {data_dir}")
    else:
        print(f"{len(entries)} records already point at {data_dir}")

    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    missing = [
        e.get("dataset_id") or e.get("artifact_id")
        for e in entries
        if (anchor := anchor_path(e)) is not None and not Path(anchor).exists()
    ]
    if missing:
        print(f"warning: store missing on disk for {', '.join(filter(None, missing))}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
