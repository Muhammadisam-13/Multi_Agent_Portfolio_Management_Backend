from datetime import date, timedelta

import pandas as pd
import pytest

from mizan.data.prices import PriceCache, cached_price_rows
from mizan.fetcher.errors import CacheMiss


def frame(n=130, last=date(2026, 10, 13)):
    days = [last - timedelta(days=i) for i in range(n)][::-1]
    return pd.DataFrame({"date": days, "open": 100.0, "high": 101.0, "low": 99.0,
                         "close": [100.0 + i for i in range(n)], "volume": pd.array(range(1000, 1000 + n), dtype="Int64"),
                         "is_anomaly": [i == 5 for i in range(n)]})


@pytest.fixture
def cache_dir(tmp_path):
    PriceCache(tmp_path).put("OGDC", frame(), {"fetched_utc": "2026-10-13T11:00:00+00:00"})
    return tmp_path


def test_default_window_is_the_last_90_days_of_the_cache(cache_dir):
    rows = cached_price_rows(cache_dir, "ogdc")
    assert rows[-1].date == date(2026, 10, 13) and rows[0].date == date(2026, 10, 13) - timedelta(days=90)
    assert [r.date for r in rows] == sorted(r.date for r in rows)
    assert rows[-1].close == 229.0 and rows[-1].volume == 1129 and rows[-1].is_anomaly is False


def test_start_and_end_select_the_rows(cache_dir):
    rows = cached_price_rows(cache_dir, "OGDC", date(2026, 10, 1), date(2026, 10, 5))
    assert [r.date for r in rows] == [date(2026, 10, d) for d in range(1, 6)]


def test_as_of_caps_the_end_so_later_prices_are_never_returned(cache_dir):
    rows = cached_price_rows(cache_dir, "OGDC", date(2026, 9, 1), date(2026, 10, 10), as_of=date(2026, 9, 10))
    assert rows[-1].date == date(2026, 9, 10)
    assert cached_price_rows(cache_dir, "OGDC", as_of=date(2026, 9, 10))[-1].date == date(2026, 9, 10)


def test_anomaly_flag_and_missing_volume_survive(cache_dir):
    df = frame(10)
    df["volume"] = pd.array([None] + list(range(9)), dtype="Int64")
    PriceCache(cache_dir).put("HBL", df, {})
    rows = cached_price_rows(cache_dir, "HBL", date(2026, 1, 1), date(2026, 12, 31))
    assert rows[0].volume is None and rows[5].is_anomaly is True


def test_no_cache_raises_cache_miss(cache_dir):
    with pytest.raises(CacheMiss, match="no cached prices"):
        cached_price_rows(cache_dir, "LUCK")


def test_start_after_end_is_a_value_error(cache_dir):
    with pytest.raises(ValueError, match="after end"):
        cached_price_rows(cache_dir, "OGDC", date(2026, 10, 5), date(2026, 10, 1))


def test_range_with_no_rows_is_empty(cache_dir):
    assert cached_price_rows(cache_dir, "OGDC", date(2020, 1, 1), date(2020, 1, 5)) == []
