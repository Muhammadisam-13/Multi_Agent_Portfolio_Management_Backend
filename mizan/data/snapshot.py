"""Frozen, versioned evidence snapshots under data/snapshots/<name>/.

Each snapshot is two files:
    items.jsonl    one EvidenceItem per line, sorted by (ticker, date, id)
    manifest.json  when and how it was built, item counts, sha256 of items.jsonl

Snapshots are never overwritten: build a new name instead, so earlier runs
stay reproducible.
"""

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from mizan.schemas import EvidenceItem


def write_snapshot(items: list[EvidenceItem], snapshot_dir: str | Path, meta: dict | None = None) -> Path:
    snapshot_dir = Path(snapshot_dir)
    if snapshot_dir.exists():
        raise FileExistsError(f"snapshot already exists, refusing to overwrite: {snapshot_dir}")

    ids = [it.id for it in items]
    dupes = [i for i, n in Counter(ids).items() if n > 1]
    if dupes:
        raise ValueError(f"duplicate evidence ids: {dupes[:5]}")

    items = sorted(items, key=lambda it: (it.ticker, it.date, it.id))
    body = "".join(json.dumps(it.to_dict(), ensure_ascii=False) + "\n" for it in items)

    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "items.jsonl").write_text(body, encoding="utf-8")

    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "item_count": len(items),
        "items_by_ticker": dict(sorted(Counter(it.ticker for it in items).items())),
        "items_by_type": dict(sorted(Counter(it.type for it in items).items())),
        "date_range": [min(it.date for it in items).isoformat(),
                       max(it.date for it in items).isoformat()] if items else None,
        "items_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        **(meta or {}),
    }
    (snapshot_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return snapshot_dir
