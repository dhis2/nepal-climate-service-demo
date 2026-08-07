"""Repoint artifact records at the data directory they are currently in.

The registry stores resolved absolute paths, so stores produced elsewhere -- in a
container, on another host -- are invisible once copied in under a different path, and
the catalogue comes up empty. Run this after copying data in; see "Where the data lives"
in README.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PATH_FIELDS = ("path", "asset_paths")


def main() -> int:
    data_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "data").resolve()
    records = data_dir / "artifacts" / "records.json"
    if not records.exists():
        print(f"no records at {records}", file=sys.stderr)
        return 1

    entries = json.loads(records.read_text())
    downloads = str(data_dir / "downloads")
    changed = 0

    def repoint(value: str) -> str:
        nonlocal changed
        # Keep the store's own filename; replace whatever directory it was written under.
        new = f"{downloads}/{Path(value).name}"
        if new != value:
            changed += 1
        return new

    for entry in entries:
        for field in PATH_FIELDS:
            value = entry.get(field)
            if isinstance(value, str):
                entry[field] = repoint(value)
            elif isinstance(value, list):
                entry[field] = [repoint(v) if isinstance(v, str) else v for v in value]

    if not changed:
        print(f"{len(entries)} records already point at {data_dir}")
        return 0

    records.write_text(json.dumps(entries, indent=2))
    print(f"repointed {changed} paths in {len(entries)} records at {data_dir}")

    missing = [
        e.get("dataset_id")
        for e in entries
        if isinstance(e.get("path"), str) and not Path(e["path"]).exists()
    ]
    if missing:
        print(f"warning: store missing on disk for {', '.join(filter(None, missing))}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
