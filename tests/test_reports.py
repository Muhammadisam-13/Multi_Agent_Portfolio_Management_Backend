import textwrap
from datetime import date

import pymupdf
import pytest

from mizan.data.reports import (
    chunk_items,
    deck_items,
    is_periodic_report,
    is_presentation,
    narrative_zone,
    select_chunks,
    select_deck_chunks,
)

NARRATIVE = ("During the year the company increased production and revenue, and the directors review the performance "
             "of its projects. The outlook is positive: demand remains strong, although inflation and interest rate "
             "risks and commodity price challenges could affect growth. The board proposes a final dividend. ")
TABLE = " ".join(f"{1000 + i}.{i:02d} {2000 + i * 3}" for i in range(80))
BOILERPLATE = ("The committee met four times; attendance is shown below. The terms of reference of the committee and the "
               "code of conduct are available. Compliance with the code of corporate governance is stated in the annexure. ")


def make_pdf(path, pages):
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((50, 60), textwrap.fill(text, 85), fontsize=9)
    doc.save(path)
    doc.close()


@pytest.fixture
def report(tmp_path):
    path = tmp_path / "report.pdf"
    make_pdf(path, [
        "Annual Report 2026 cover page",                                              # p1: before the review
        "Chairman's Review. " + NARRATIVE * 2,                                        # p2: narrative zone starts
        "Directors' Report. " + BOILERPLATE * 3,                                      # p3: boilerplate, lower value
        NARRATIVE + TABLE,                                                            # p4: mostly a table
        "Independent Auditor's Report to the members. " + NARRATIVE * 2,              # p5: zone ends before this page
        "Notes to the financial statements. " + NARRATIVE * 3,                        # p6: after the auditor's report
    ])
    return path


# --- the narrative zone ---------------------------------------------------------

def test_zone_runs_from_the_first_review_heading_to_the_page_before_the_auditor():
    pages = ["cover", "Contents", "Chairman's Review text", "more", "Independent Auditor's Report", "notes"]
    assert narrative_zone(pages) == (2, 3)


def test_zone_falls_back_to_the_whole_document():
    assert narrative_zone(["a", "b", "c"]) == (0, 2)


@pytest.mark.parametrize("heading", ["Managing Director's Review", "Directors' Report", "CEO message",
                                     "Chairman’s Message", "Management Discussion and Analysis"])
def test_review_headings_are_recognised(heading):
    start, _ = narrative_zone(["cover", heading + " ...", "x"])
    assert start == 1


# --- chunk selection -------------------------------------------------------------

def test_only_zone_pages_are_searched(report):
    pages = {c.page for c in select_chunks(report)}
    assert pages <= {2, 3, 4}                      # never the cover (1) or anything after the auditor's report (5, 6)
    assert 2 in pages


def test_table_like_text_is_dropped(report):
    assert all("1000.00 2000" not in c.text for c in select_chunks(report))


def test_narrative_beats_boilerplate(report):
    chunks = select_chunks(report, max_chunks=1)
    assert chunks[0].page == 2


def test_limits_per_page_cap_and_page_order(tmp_path):
    path = tmp_path / "long_narrative.pdf"
    make_pdf(path, ["Chairman's Review. " + NARRATIVE * 5, NARRATIVE * 5, NARRATIVE * 5])   # 3 pages, several chunks each

    everything = select_chunks(path, max_chunks=20, target_chars=600, per_page=10)
    assert len(everything) >= 6
    assert [(c.page, c.index) for c in everything] == sorted((c.page, c.index) for c in everything)   # page order

    assert len(select_chunks(path, max_chunks=3, target_chars=600, per_page=10)) == 3               # max_chunks respected
    capped = select_chunks(path, max_chunks=20, target_chars=600, per_page=1)
    assert [c.page for c in capped] == [1, 2, 3]                                                    # one per page
    assert all(sum(1 for c in select_chunks(path, 20, 600, per_page=2) if c.page == p) <= 2 for p in (1, 2, 3))


def test_selection_is_deterministic(report):
    assert select_chunks(report) == select_chunks(report)


# --- evidence items --------------------------------------------------------------

def test_items_carry_ticker_date_page_and_stable_ids(report):
    items = chunk_items("alph", "900003", date(2026, 8, 27), "Transmission of Annual Report for the Year Ended June 30, 2026 ", report)
    assert items and all(i.ticker == "ALPH" and i.date == date(2026, 8, 27) for i in items)
    assert all(i.type == "report_section" and i.source == "psx_report" for i in items)
    assert items[0].id.startswith("ALPH-REPORT-900003-p002-")
    assert len({i.id for i in items}) == len(items)
    assert "page 2 of 6" in items[0].text and "Transmission of Annual Report" in items[0].text
    assert [i.id for i in items] == [i.id for i in chunk_items("ALPH", "900003", date(2026, 8, 27), "x", report)]


def test_report_without_usable_text_gives_one_flagged_item(tmp_path):
    scanned = tmp_path / "scan.pdf"
    make_pdf(scanned, ["", "", ""])
    items = chunk_items("ALPH", "900005", date(2026, 8, 27), "Annual Report", scanned)
    assert len(items) == 1 and items[0].id == "ALPH-REPORT-900005-none" and "OCR" in items[0].text


@pytest.mark.parametrize("title, expected", [
    ("Transmission of Annual Report for the Year Ended June 30, 2026", True),
    ("Transmission of Quarterly Report for the period ended - Marach 31, 2026", True),
    ("Transmission of Half Yearly Report for the Period Ended June 30, 2026.", True),
    ("Transmission of Half-Yearly Report", True),
    ("FINANCIAL RESULTS FOR THE YEAR ENDED JUNE 30, 2026", False),
    ("Notice of Annual General Meeting", False),
    ("Presentation for the Corporate Briefing Session", False),
    ("Material Information", False),
])
def test_only_periodic_reports_are_chunked(title, expected):
    assert is_periodic_report(title) is expected


def test_contents_page_does_not_fool_the_zone_search():
    pages = ["cover", "Contents Chairman's Review 5 Directors' Report 9 Independent Auditor's Report 60"]
    pages += ["front matter"] * 8                                    # pages 3-10
    pages += ["Chairman's Review. The year was good."]                # page 11 (index 10): the real start
    pages += ["narrative"] * 48
    pages += ["Independent Auditor's Report to the members."]         # index 59
    pages += ["financial statements"] * 40
    assert len(pages) == 100
    assert narrative_zone(pages) == (10, 58)


def test_zone_without_any_heading_or_contents_covers_the_whole_document():
    assert narrative_zone(["x"] * 100) == (0, 99)
    assert narrative_zone(["x"] * 30) == (0, 29)
    assert narrative_zone(["x"]) == (0, 0)
    assert narrative_zone([]) == (0, -1)


@pytest.mark.parametrize("heading", ["Unconsolidated Statement of Financial Position As at June 30",
                                     "CONSOLIDATED STATEMENT OF PROFIT OR LOSS", "Notes to the Financial Statements",
                                     "Condensed Interim Statement of Cash Flows"])
def test_a_page_opening_with_a_financial_statement_ends_the_zone(heading):
    pages = ["cover", "contents", "Chairman's Review. text"] + ["narrative"] * 8 + [heading + " 123 456"] + ["more notes"] * 5
    assert narrative_zone(pages) == (2, 10)


def test_analysis_pages_inside_the_narrative_do_not_end_the_zone():
    pages = ["cover", "contents", "Chairman's Review. text"] + ["narrative"] * 5 + ["ANALYSIS OF STATEMENT OF FINANCIAL POSITION PKR 2021"] + ["narrative"] * 5
    assert narrative_zone(pages)[1] == len(pages) - 1


def test_short_contents_page_is_skipped_too():
    pages = ["cover", "CONTENTS 07 03 Company Information 04 Directors' Review 09 Condensed Interim Financial Statements",
             "Directors' Review for the quarter. The company performed well."] + ["narrative"] * 6 +             ["Condensed Interim Statement of Financial Position As at March 31 123 456"] + ["notes"] * 4
    assert narrative_zone(pages) == (2, 8)


def test_a_running_header_before_the_statement_heading_still_ends_the_zone():
    pages = ["cover", "contents", "Directors' Report text"] + ["narrative"] * 8 +             ["Nine Monthly Report 2025-26 17 Condensed Interim Statement of Financial Position As at March 31"] + ["notes"] * 4
    assert narrative_zone(pages) == (2, 10)


@pytest.mark.parametrize("heading", ["HORIZONTAL AND VERTICAL ANALYSIS OF STATEMENT OF PROFIT OR LOSS",
                                     "Summary of statement of cash flows", "Financial ratios: statement of financial position"])
def test_analysis_sections_do_not_end_the_zone(heading):
    pages = ["cover", "contents", "Directors' Report text"] + ["narrative"] * 5 + [heading] + ["narrative"] * 5
    assert narrative_zone(pages)[1] == len(pages) - 1


@pytest.mark.parametrize("title, expected", [
    ("Presentation for the Corporate Briefing Session of The Hub Power Company Limited", True),
    ("Final Presentation - Second Corporate Briefing (CBS) of 2026", True),
    ("Notice of Corporate Briefing Session", True),
    ("Transmission of Annual Report", False),
    ("Material Information", False),
])
def test_presentations_are_recognised_by_title(title, expected):
    assert is_presentation(title) is expected


SLIDES = ["Investor briefing Q1 2026",
          "Agenda: company at a glance, performance, outlook",
          "Performance: revenue growth of 15% and profit increased on strong demand in the Middle East.",
          "",
          "Outlook: we expect growth to continue, although inflation and currency risk remain challenges.",
          "Q&A"]


def test_deck_groups_consecutive_slides_and_skips_empty_ones(tmp_path):
    path = tmp_path / "deck.pdf"
    make_pdf(path, [s * 3 for s in SLIDES])                               # slide 4 stays empty
    chunks = select_deck_chunks(path, max_chunks=5, target_chars=300)
    assert chunks
    assert [c.page for c in chunks] == sorted(c.page for c in chunks)     # slide order
    assert all(len(c.text) >= 200 for c in chunks)
    assert any("Outlook" in c.text for c in chunks) and any("Performance" in c.text for c in chunks)
    assert all(c.page != 4 for c in chunks)                               # a group never starts on the empty slide


def test_deck_keeps_only_the_best_scoring_groups(tmp_path):
    path = tmp_path / "deck.pdf"
    make_pdf(path, [s * 3 for s in SLIDES])
    assert len(select_deck_chunks(path, max_chunks=1, target_chars=300)) == 1


def test_deck_items_carry_ticker_date_slide_and_stable_ids(tmp_path):
    path = tmp_path / "deck.pdf"
    make_pdf(path, [s * 4 for s in SLIDES])                                # longer slides so groups pass the minimum size
    items = deck_items("alph", "900007", date(2026, 6, 2), "Presentation of Corporate Briefing Session", path, target_chars=300)
    assert items and all(i.ticker == "ALPH" and i.date == date(2026, 6, 2) for i in items)
    assert all(i.type == "presentation_section" and i.source == "psx_presentation" for i in items)
    assert items[0].id.startswith("ALPH-DECK-900007-p") and "from slide" in items[0].text
    assert len({i.id for i in items}) == len(items)


def test_deck_without_text_gives_nothing(tmp_path):
    path = tmp_path / "scan.pdf"
    make_pdf(path, ["", "", ""])
    assert deck_items("ALPH", "900008", date(2026, 6, 2), "Presentation", path) == []
