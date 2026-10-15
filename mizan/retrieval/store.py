"""A verified snapshot loaded once and queried by ticker, date and id (what the API serves from).

The store never touches the network: it reads items.jsonl from a snapshot folder after checking it against its
manifest (verify_snapshot), so a damaged or edited file is refused with a readable reason.
"""

import json
from collections import Counter
from datetime import date
from pathlib import Path

from mizan.data.snapshot import verify_snapshot
from mizan.retrieval.bundle import build_bundle, load_items
from mizan.schemas import EvidenceBundle, EvidenceItem


class SnapshotError(Exception):
    """The snapshot is missing, does not match its manifest, or cannot be read."""


def resolve_snapshot_folder(snapshot: str | Path, snapshots_dir: str | Path) -> Path:
    """A snapshot given as an existing path, or as a name under snapshots_dir."""
    path = Path(snapshot)
    return path if path.exists() else Path(snapshots_dir) / path


class SnapshotStore:
    def __init__(self, folder: Path, items: list[EvidenceItem], manifest: dict):
        self.folder = folder
        self.name = folder.name
        self.items = items
        self.manifest = manifest
        self._by_id = {i.id: i for i in items}
        self._count_by_ticker = Counter(i.ticker for i in items)

    @classmethod
    def load(cls, folder: str | Path) -> "SnapshotStore":
        folder = Path(folder)
        try:
            verify_snapshot(folder)
            items = load_items(folder / "items.jsonl")
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise SnapshotError(f"snapshot '{folder.name}' is missing a file: {exc.filename or exc}") from exc
        except (ValueError, KeyError) as exc:       # includes JSON errors and the hash mismatch from verify_snapshot
            raise SnapshotError(str(exc)) from exc
        ids = Counter(i.id for i in items)
        dupes = [i for i, n in ids.items() if n > 1]
        if dupes:
            raise SnapshotError(f"snapshot '{folder.name}' has duplicate evidence ids, e.g. {dupes[:3]}")
        return cls(folder, items, manifest)

    # --- queries ---------------------------------------------------------------------
    def bundle(self, ticker: str, as_of: date) -> EvidenceBundle:
        """The ticker's items and MACRO items dated on or before as_of (rules 1 and 2)."""
        return build_bundle(self.items, ticker, as_of)

    def get(self, item_id: str, as_of: date | None = None) -> EvidenceItem | None:
        """One item by id. With as_of, an item dated after it counts as not found (no look-ahead)."""
        item = self._by_id.get(item_id)
        return item if item is not None and (as_of is None or item.date <= as_of) else None

    def latest_date(self) -> date | None:
        return max((i.date for i in self.items), default=None)

    def item_count_for(self, ticker: str) -> int:
        return self._count_by_ticker.get(ticker.upper(), 0)

    def tickers(self) -> list[str]:
        return sorted(t for t in self._count_by_ticker if t != "MACRO")

    def summary(self) -> dict:
        """What the UI shows about the data in use."""
        dates = [i.date for i in self.items]
        return {
            "name": self.name,
            "item_count": len(self.items),
            "date_range": [min(dates).isoformat(), max(dates).isoformat()] if dates else None,
            "tickers": self.tickers(),
            "items_by_type": dict(sorted(Counter(i.type for i in self.items).items())),
            "created_utc": self.manifest.get("created_utc"),
            "verified": True,
        }
