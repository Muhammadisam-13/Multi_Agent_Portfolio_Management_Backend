from datetime import date

import pandas as pd
import pytest

from mizan.data import prices
from mizan.data.prices import PriceLoader, validate_history
from mizan.fetcher.client import Throttle
from mizan.fetcher.config import FetchConfig
from mizan.fetcher.errors import (
    BlockedError,
    CacheMiss,
    FetchError,
    LiveFetchDisabled,
    StructureChangedError,
)

TODAY = date(2026, 10, 13)


def history(n=5, start="2026-10-05"):
    days = pd.bdate_range(start, periods=n)[::-1]          # newest first, like psxdata
    return pd.DataFrame({
        "date": days,
        "open": [100.0 + i for i in range(n)],
        "high": [101.0 + i for i in range(n)],
        "low": [99.0 + i for i in range(n)],
        "close": [100.5 + i for i in range(n)],
        "volume": pd.array([1000 * (i + 1) for i in range(n)], dtype="Int64"),
        "is_anomaly": [False] * n,
    })


class FakeFetch:
    def __init__(self, *results):
        self.results, self.calls = list(results), []

    def __call__(self, ticker):
        self.calls.append(ticker)
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class FakeTime:
    def __init__(self):
        self.now, self.sleeps = 0.0, []

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s

    def clock(self):
        return self.now


def loader(tmp_path, *results, live=True):
    fetch, t = FakeFetch(*results), FakeTime()
    cfg = FetchConfig(live=live, cache_dir=tmp_path, min_interval_s=5)
    return PriceLoader(cfg, fetch=fetch, throttle=Throttle(5, t.sleep, t.clock), today=lambda: TODAY), fetch, t


# --- cache behaviour ----------------------------------------------------------

def test_first_live_call_fetches_once_and_caches(tmp_path):
    pl, fetch, _ = loader(tmp_path, history())
    h = pl.load_history("ogdc")
    assert not h.from_cache and fetch.calls == ["OGDC"]
    assert list(h.df["date"]) == sorted(h.df["date"])          # oldest first
    assert (tmp_path / "prices" / "OGDC.csv").exists()

    again = pl.load_history("OGDC")
    assert again.from_cache and fetch.calls == ["OGDC"]         # no second request
    pd.testing.assert_frame_equal(again.df, h.df, check_dtype=False)


def test_offline_reads_cache_and_never_fetches(tmp_path):
    loader(tmp_path, history())[0].load_history("OGDC")
    offline, fetch, _ = loader(tmp_path, live=False)
    assert offline.load_history("OGDC").from_cache and fetch.calls == []


def test_offline_without_cache_is_a_cache_miss(tmp_path):
    with pytest.raises(CacheMiss, match="--live"):
        loader(tmp_path, live=False)[0].load_history("OGDC")


def test_refresh_needs_live(tmp_path):
    loader(tmp_path, history())[0].load_history("OGDC")
    with pytest.raises(LiveFetchDisabled):
        loader(tmp_path, live=False)[0].load_history("OGDC", refresh=True)


def test_refresh_refetches_and_updates_cache(tmp_path):
    pl, fetch, _ = loader(tmp_path, history(5), history(6))
    pl.load_history("OGDC")
    h = pl.load_history("OGDC", refresh=True)
    assert len(h.df) == 6 and fetch.calls == ["OGDC", "OGDC"]


def test_refresh_with_fewer_rows_is_rejected_and_cache_kept(tmp_path):
    pl, _, _ = loader(tmp_path, history(6), history(3))
    pl.load_history("OGDC")
    with pytest.raises(StructureChangedError, match="fewer"):
        pl.load_history("OGDC", refresh=True)
    assert len(pl.load_history("OGDC").df) == 6


def test_live_calls_are_spaced_by_the_throttle(tmp_path):
    pl, _, t = loader(tmp_path, history(), history())
    pl.load_history("OGDC")
    pl.load_history("HBL")
    assert t.sleeps == [5]


# --- validation -----------------------------------------------------------------

@pytest.mark.parametrize("bad, match", [
    (history().iloc[0:0], "no price rows"),
    (history().drop(columns=["close"]), "missing columns"),
    (pd.concat([history(), history().iloc[[0]]]), "duplicate"),
    (history(start="2026-10-12", n=5), "implausible date range"),       # runs past "today"
])
def test_bad_psxdata_output_is_rejected_and_not_cached(tmp_path, bad, match):
    pl, _, _ = loader(tmp_path, bad)
    with pytest.raises(StructureChangedError, match=match):
        pl.load_history("OGDC")
    assert not (tmp_path / "prices" / "OGDC.csv").exists()


def test_load_prices_slices_the_cached_history(tmp_path):
    pl, _, _ = loader(tmp_path, history(5, start="2026-10-05"))    # 5..9 Oct
    df = pl.load_prices("OGDC", date(2026, 10, 6), date(2026, 10, 8))
    assert list(df["date"]) == [date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)]


def test_load_prices_with_empty_range_raises(tmp_path):
    pl, _, _ = loader(tmp_path, history())
    with pytest.raises(ValueError, match="no price rows"):
        pl.load_prices("OGDC", date(2020, 1, 1), date(2020, 1, 31))


# --- failures from psxdata --------------------------------------------------------

def test_token_refusal_fails_loudly_without_retry(tmp_path, monkeypatch):
    from psxdata.exceptions import PSXAuthError
    import psxdata

    calls = []

    def refused(symbol, cache):
        calls.append(symbol)
        raise PSXAuthError("PSX auth error (403)")

    monkeypatch.setattr(psxdata, "stocks", refused)
    pl = PriceLoader(FetchConfig(live=True, cache_dir=tmp_path), throttle=Throttle(0), today=lambda: TODAY)
    with pytest.raises(BlockedError, match="X-Req-Id token"):
        pl.load_history("OGDC")
    assert calls == ["OGDC"]                                     # one call, no extra retries from us
    assert not (tmp_path / "prices" / "OGDC.csv").exists()


def test_wrong_psxdata_version_is_refused(tmp_path, monkeypatch):
    import psxdata
    monkeypatch.setattr(psxdata, "__version__", "9.9.9")
    pl = PriceLoader(FetchConfig(live=True, cache_dir=tmp_path), throttle=Throttle(0), today=lambda: TODAY)
    with pytest.raises(FetchError, match="pinned"):
        pl.load_history("OGDC")


def test_pinned_version_matches_requirements():
    from pathlib import Path
    reqs = (Path(prices.__file__).parents[2] / "requirements.txt").read_text(encoding="utf-8")
    assert f"psxdata=={prices.PSXDATA_VERSION}" in reqs
