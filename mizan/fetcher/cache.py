"""Local page cache under data/cache/ (git-ignored).

Each fetched page is kept as <cache_dir>/<namespace>/<UTC timestamp>.html next to a
small .json file recording the URL and fetch time. Pages are never overwritten, so
older copies stay available for audit. Only pages that passed validation are stored.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from mizan.fetcher.client import PoliteClient
from mizan.fetcher.config import FetchConfig
from mizan.fetcher.errors import CacheMiss, FetchError

STAMP = "%Y%m%dT%H%M%SZ"


@dataclass(frozen=True)
class CachedPage:
    text: str
    url: str
    fetched_utc: datetime
    path: Path


class PageCache:
    def __init__(self, root: Path):
        self.root = Path(root)

    def latest(self, namespace: str) -> CachedPage | None:
        folder = self.root / namespace
        pages = sorted(folder.glob("*.html")) if folder.exists() else []
        if not pages:
            return None
        path = pages[-1]
        meta = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        return CachedPage(
            text=path.read_text(encoding="utf-8"),
            url=meta["url"],
            fetched_utc=datetime.fromisoformat(meta["fetched_utc"]),
            path=path,
        )

    def put(self, namespace: str, text: str, url: str, fetched_utc: datetime) -> CachedPage:
        folder = self.root / namespace
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{fetched_utc.strftime(STAMP)}.html"
        path.write_text(text, encoding="utf-8")
        path.with_suffix(".json").write_text(
            json.dumps({"url": url, "fetched_utc": fetched_utc.isoformat()}), encoding="utf-8")
        return CachedPage(text, url, fetched_utc, path)


def load_cached(namespace: str, source: str, config: FetchConfig, cache: PageCache,
                fetch: Callable[[], str], validate: Callable[[str], object],
                now: datetime | None = None) -> tuple[CachedPage, str | None]:
    """Return (page, warning). Uses the cache unless live fetching is on and the copy is stale.

    - live off: the newest cached copy, or CacheMiss if there is none.
    - live on, fresh copy cached: the cached copy (no request).
    - live on, no/stale copy: fetch() it, run validate() (raises if the page structure changed),
      then cache it. If the fetch fails but an older copy exists, that copy is returned with a
      warning saying so; with no older copy the error propagates.

    A refusal (BlockedError) is never swallowed into a cache fallback for a first fetch, and
    callers decide what to do with the warning.
    """
    now = now or datetime.now(timezone.utc)
    cached = cache.latest(namespace)

    if not config.live:
        if cached is None:
            raise CacheMiss(f"nothing cached for '{namespace}' and live fetching is off")
        return cached, None

    if cached is not None and now - cached.fetched_utc <= timedelta(hours=config.max_age_hours):
        return cached, None

    try:
        text = fetch()
        validate(text)
    except FetchError as exc:
        if cached is None:
            raise
        return cached, (f"live fetch of '{namespace}' failed ({type(exc).__name__}: {exc}); "
                        f"using cached copy from {cached.fetched_utc.isoformat()}")
    return cache.put(namespace, text, source, now), None


def load_page(namespace: str, url: str, config: FetchConfig, client: PoliteClient,
              cache: PageCache, validate: Callable[[str], object],
              now: datetime | None = None) -> tuple[CachedPage, str | None]:
    """load_cached() for a page fetched with a plain GET of url."""
    return load_cached(namespace, url, config, cache, lambda: client.get_text(url), validate, now)
