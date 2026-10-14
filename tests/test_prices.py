from datetime import date

import pandas as pd
import pytest

from mizan.data.prices import prices_to_items, validate_prices

START, END = date(2025, 6, 1), date(2025, 6, 30)


def raw_frame():
    # newest first, like psxdata returns it
    return pd.DataFrame({
        "date": pd.to_datetime(["2025-06-27", "2025-06-26", "2025-06-25"]),
        "open": [217.5, 218.0, 215.0],
        "high": [226.0, 222.49, 219.0],
        "low": [216.75, 216.11, 214.0],
        "close": [221.19, 217.29, 218.0],
        "volume": pd.array([9560957, 6966647, 100], dtype="Int64"),
        "is_anomaly": [False, False, True],
    })


def test_validate_sorts_oldest_first():
    df = validate_prices(raw_frame(), "OGDC", START, END)
    assert list(df["date"]) == [date(2025, 6, 25), date(2025, 6, 26), date(2025, 6, 27)]


@pytest.mark.parametrize("bad", [
    pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "is_anomaly"]),  # empty
    raw_frame().drop(columns=["close"]),                                                   # missing column
    pd.concat([raw_frame(), raw_frame().iloc[[0]]]),                                       # duplicate date
])
def test_validate_rejects_bad_frames(bad):
    with pytest.raises(ValueError):
        validate_prices(bad, "OGDC", START, END)


def test_validate_rejects_rows_outside_range():
    with pytest.raises(ValueError, match="outside"):
        validate_prices(raw_frame(), "OGDC", START, date(2025, 6, 26))


def test_prices_to_items():
    items = prices_to_items("ogdc", validate_prices(raw_frame(), "OGDC", START, END))
    assert [it.id for it in items] == ["OGDC-PRICE-2025-06-25", "OGDC-PRICE-2025-06-26", "OGDC-PRICE-2025-06-27"]
    assert all(it.ticker == "OGDC" and it.type == "price" for it in items)
    assert "anomaly" in items[0].text            # flagged row says so
    assert "vs previous close" not in items[0].text  # first day has no earlier close
    assert "-0.33% vs previous close 218.00" in items[1].text
    assert "close 221.19 PKR" in items[2].text and "9,560,957" in items[2].text
