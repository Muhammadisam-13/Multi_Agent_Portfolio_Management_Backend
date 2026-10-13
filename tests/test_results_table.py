import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from mizan.fetcher.cache import PageCache
from mizan.fetcher.client import PoliteClient
from mizan.fetcher.config import FetchConfig
from mizan.fetcher.errors import BlockedError, CacheMiss, StructureChangedError
from mizan.fetcher.results_table import (
    URL,
    FinancialResultsFetcher,
    load_name_map,
    normalize_name,
    parse_results_page,
    rows_to_items,
)
from mizan.retrieval.bundle import build_bundle

SAMPLE = (Path(__file__).parent / "fixtures" / "psx" / "financial_announcements_sample.html").read_text(encoding="utf-8")
NAME_MAP = {
    normalize_name("Alpha Oil & Gas Limited"): "ALPH",
    normalize_name("Beta Bank Limited"): "BETA",
    normalize_name("Gamma Textile Mills Limited"): "GAMT",
}


def items_by_id():
    rows, _ = parse_results_page(SAMPLE)
    items, _ = rows_to_items(rows, NAME_MAP)
    return {it.id: it for it in items}


# --- parsing ------------------------------------------------------------------

def test_parse_reads_rows_with_their_date_headers():
    rows, problems = parse_results_page(SAMPLE)
    assert problems == []
    assert len(rows) == 7
    assert rows[0].company == "Alpha Oil & Gas Limited" and rows[0].day == date(2026, 10, 12)
    assert rows[-1].day == date(2026, 4, 13)


def test_parse_ignores_the_unrelated_first_table():
    rows, _ = parse_results_page(SAMPLE)
    assert all(r.company != "FAKE" for r in rows)


def test_missing_table_is_a_structure_change():
    with pytest.raises(StructureChangedError, match="no results table"):
        parse_results_page("<html><body><p>Under maintenance</p></body></html>")


def test_renamed_columns_are_a_structure_change():
    with pytest.raises(StructureChangedError, match="columns changed"):
        parse_results_page(SAMPLE.replace("<td>Company</td>", "<td>Company</td>", 1)
                                 .replace("Closure Of Share Transfer Books", "Something Else"))


def test_unreadable_date_header_is_a_structure_change():
    with pytest.raises(StructureChangedError, match="date header"):
        parse_results_page(SAMPLE.replace("Oct 12, 2026", "12th October"))


def test_header_only_table_is_a_structure_change():
    head = SAMPLE[:SAMPLE.index('<tr><th colspan="9">')] + "</table></body></html>"
    with pytest.raises(StructureChangedError, match="no data rows"):
        parse_results_page(head)


def test_malformed_rows_are_reported_but_tolerated_up_to_a_limit():
    broken = SAMPLE.replace("<td>Unlisted Sugar Mills Limited</td><td>11:00:00</td>", "<td>Unlisted Sugar Mills Limited</td>")
    rows, problems = parse_results_page(broken, max_skipped_fraction=0.2)
    assert len(rows) == 6 and len(problems) == 1 and "Unlisted Sugar" in problems[0]
    with pytest.raises(StructureChangedError, match="unreadable"):
        parse_results_page(broken, max_skipped_fraction=0.05)


# --- evidence items -----------------------------------------------------------

def test_dates_ids_and_tickers():
    items = items_by_id()
    ucs = items["ALPH-RESULT-2026-10-12-20260630YR-UNCONSOLIDATED-125126"]
    assert ucs.ticker == "ALPH" and ucs.date == date(2026, 10, 12)
    assert ucs.source == "psx_financial_announcements" and ucs.type == "financial_results"
    assert len(items) == 6                      # the unmapped sugar company is not an item


def test_consolidated_and_unconsolidated_rows_are_both_kept_and_labelled():
    items = items_by_id()
    cs = items["ALPH-RESULT-2026-10-12-20260630YR-CONSOLIDATED-125242"]
    ucs = items["ALPH-RESULT-2026-10-12-20260630YR-UNCONSOLIDATED-125126"]
    assert "(consolidated)" in cs.text and "259133.104" in cs.text
    assert "(unconsolidated)" in ucs.text and "259,134.869" in ucs.text
    assert "Dividend/bonus/right as announced: 60% (F) (D)" in ucs.text   # code passed through verbatim
    assert "Dividend" not in cs.text


def test_text_states_period_units_and_meeting_details():
    text = items_by_id()["ALPH-RESULT-2026-10-12-20260630YR-UNCONSOLIDATED-125126"].text
    assert "year ended 30 June 2026" in text
    assert "profit after taxation Rs 242,373.646 million" in text
    assert "earnings per share Rs 56.35" in text
    assert "16/10/2026" in text and "09/10/2026 - 16/10/2026" in text


def test_loss_is_spelled_out_not_left_as_parentheses():
    text = items_by_id()["BETA-RESULT-2026-10-12-20260930IQ-UNCONSOLIDATED-151000"].text
    assert "first quarter ended 30 September 2026" in text
    assert "profit after taxation (loss) of Rs 12.398 million" in text
    assert "earnings per share (loss per share) of Rs 0.45" in text


def test_row_without_period_or_figures_becomes_a_notice():
    notice = items_by_id()["GAMT-NOTICE-2026-10-09-163607"]
    assert notice.type == "corporate_notice"
    assert "no financial figures" in notice.text and "31/10/2026(EOGM)" in notice.text


def test_ids_are_unique_and_stable_across_runs():
    first, second = items_by_id(), items_by_id()
    assert list(first) == list(second) and len(first) == 6


def test_unmatched_companies_are_counted_not_guessed():
    rows, _ = parse_results_page(SAMPLE)
    items, unmatched = rows_to_items(rows, NAME_MAP)
    assert unmatched == {"Unlisted Sugar Mills Limited": 1}
    assert all(it.ticker in {"ALPH", "BETA", "GAMT"} for it in items)


def test_ticker_filter_keeps_only_requested_tickers():
    rows, _ = parse_results_page(SAMPLE)
    items, _ = rows_to_items(rows, NAME_MAP, tickers=["beta"])
    assert {it.ticker for it in items} == {"BETA"}


def test_results_feed_the_as_of_filter_without_leakage():
    rows, _ = parse_results_page(SAMPLE)
    items, _ = rows_to_items(rows, NAME_MAP)
    bundle = build_bundle(items, "ALPH", date(2026, 10, 9))
    assert {it.date for it in bundle.items} == {date(2026, 10, 9)}   # the 12 Oct results are in the future
    assert all(it.ticker == "ALPH" for it in bundle.items)


# --- ticker name file ---------------------------------------------------------

def test_repo_ticker_names_file_loads():
    mapping = load_name_map()
    assert mapping[normalize_name("oil & gas development company limited")] == "OGDC"


def test_name_mapped_to_two_tickers_is_rejected(tmp_path):
    path = tmp_path / "names.json"
    path.write_text(json.dumps({"AAA": ["Same Name Ltd"], "BBB": ["same  name ltd"]}), encoding="utf-8")
    with pytest.raises(ValueError, match="both"):
        load_name_map(path)


# --- the fetcher end to end (fake network, temp cache) -------------------------

class FakeSession:
    def __init__(self, status=200, text=SAMPLE):
        self.status, self.text, self.calls = status, text, 0

    def get(self, url, headers, timeout):
        self.calls += 1
        assert url == URL
        return type("R", (), {"status_code": self.status, "text": self.text})()


def make_fetcher(tmp_path, live, session=None):
    cfg = FetchConfig(live=live, cache_dir=tmp_path, min_interval_s=0)
    client = PoliteClient(cfg, session=session or FakeSession(), sleep=lambda s: None)
    return FinancialResultsFetcher(cfg, name_map=NAME_MAP, client=client, cache=PageCache(tmp_path))


def test_offline_with_no_cache_raises_cache_miss(tmp_path):
    with pytest.raises(CacheMiss):
        make_fetcher(tmp_path, live=False).fetch(["ALPH"])


def test_live_fetch_then_offline_run_from_cache(tmp_path):
    session = FakeSession()
    live = make_fetcher(tmp_path, live=True, session=session).fetch(["ALPH", "BETA"])
    assert len(live.items) == 5 and session.calls == 1

    offline_session = FakeSession()
    offline = make_fetcher(tmp_path, live=False, session=offline_session).fetch(["ALPH", "BETA"])
    assert [it.id for it in offline.items] == [it.id for it in live.items]
    assert offline_session.calls == 0


def test_warns_about_requested_ticker_with_no_rows(tmp_path):
    result = make_fetcher(tmp_path, live=True).fetch(["ALPH", "ZZZZ"])
    assert any("no results rows for ZZZZ" in w for w in result.warnings)
    assert not any("no results rows for ALPH" in w for w in result.warnings)


def test_blocked_with_no_cache_raises_and_with_cache_warns(tmp_path):
    with pytest.raises(BlockedError):
        make_fetcher(tmp_path, live=True, session=FakeSession(status=403)).fetch(["ALPH"])

    PageCache(tmp_path).put("financial_announcements", SAMPLE, URL, datetime(2026, 10, 1, tzinfo=timezone.utc))
    result = make_fetcher(tmp_path, live=True, session=FakeSession(status=403)).fetch(["ALPH"])
    assert len(result.items) > 0
    assert any("BlockedError" in w and "using cached copy" in w for w in result.warnings)


def test_redesigned_page_is_rejected_and_not_cached(tmp_path):
    session = FakeSession(text="<html><body>New design</body></html>")
    with pytest.raises(StructureChangedError):
        make_fetcher(tmp_path, live=True, session=session).fetch(["ALPH"])
    assert PageCache(tmp_path).latest("financial_announcements") is None
