from datetime import date
from pathlib import Path

import pymupdf
import pytest

from mizan.fetcher.announcements import (
    AnnouncementRow,
    AnnouncementsFetcher,
    DocText,
    PdfCache,
    describe_document,
    parse_announcements_page,
    row_to_item,
)
from mizan.fetcher.cache import PageCache
from mizan.fetcher.config import FetchConfig
from mizan.fetcher.errors import BlockedError, CacheMiss, FetchTimeout, StructureChangedError
from mizan.retrieval.bundle import build_bundle

SAMPLE = (Path(__file__).parent / "fixtures" / "psx" / "announcements_sample.html").read_text(encoding="utf-8")
EMPTY = ('<div data-total="0"></div><table id="announcementsTable"><thead><tr><th>DATE</th><th>TIME</th><th>SYMBOL</th>'
         '<th>NAME</th><th>TITLE</th><th></th></tr></thead><tbody></tbody></table>')


LETTER_PAD = "\nThe board met and approved the matter described in this letter to the exchange and the shareholders."


BODY = ("\nWe are pleased to announce the results of the company for the period.") * 6


def make_pdf(path, pages):
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def pdf_bytes(tmp_path, pages):
    path = tmp_path / "tmp.pdf"
    make_pdf(path, pages)
    return path.read_bytes()


# --- parsing ------------------------------------------------------------------

def test_parse_reads_rows_total_and_document_ids():
    rows, total, problems = parse_announcements_page(SAMPLE)
    assert total == 5 and problems == [] and len(rows) == 5
    first = rows[0]
    assert (first.day, first.time, first.symbol) == (date(2026, 9, 9), "9:16 AM", "ALPH")
    assert first.name == "Alpha Oil & Gas Limited" and first.title == "Material Information" and first.doc_id == "900001"
    assert rows[3].doc_id == "900004"                 # a row with no "View" image link still has its PDF
    assert rows[4].doc_id is None                     # a row with no document at all


def test_empty_result_is_an_empty_list_not_an_error():
    assert parse_announcements_page(EMPTY) == ([], 0, [])


def test_missing_table_columns_and_counter_are_structure_changes():
    with pytest.raises(StructureChangedError, match="not found"):
        parse_announcements_page("<html>maintenance</html>")
    with pytest.raises(StructureChangedError, match="columns changed"):
        parse_announcements_page(SAMPLE.replace("<th>TITLE</th>", "<th>SUBJECT</th>"))
    with pytest.raises(StructureChangedError, match="data-total"):
        parse_announcements_page(SAMPLE.replace("data-total", "data-count"))


def test_unreadable_rows_are_reported_up_to_a_limit():
    broken = SAMPLE.replace("Sep 9, 2026", "9th September")
    rows, _, problems = parse_announcements_page(broken, max_skipped_fraction=0.5)
    assert len(rows) == 4 and len(problems) == 1 and "9th September" in problems[0]
    with pytest.raises(StructureChangedError, match="unreadable"):
        parse_announcements_page(broken)


# --- documents ----------------------------------------------------------------

def test_short_text_pdf_is_described_with_its_text(tmp_path):
    make_pdf(tmp_path / "a.pdf", ["Subject: First Gas from the Lundali Well.\nWe are pleased to announce." + LETTER_PAD])
    doc = describe_document(tmp_path / "a.pdf", max_pdf_pages=8, max_text_chars=4000)
    assert doc.status == "text" and doc.pages == 1
    assert "First Gas from the Lundali Well. We are pleased" in doc.text      # whitespace collapsed


def test_text_is_truncated_at_the_limit(tmp_path):
    make_pdf(tmp_path / "a.pdf", ["word word word word word\n" * 30])      # several lines so the page really holds >100 chars
    doc = describe_document(tmp_path / "a.pdf", 8, max_text_chars=100)
    assert doc.text.endswith("[truncated]") and len(doc.text) < 130


def test_scanned_pdf_is_flagged_not_returned_empty(tmp_path):
    make_pdf(tmp_path / "scan.pdf", [""])
    assert describe_document(tmp_path / "scan.pdf", 8, 4000).status == "needs_ocr"


def test_long_document_keeps_its_opening(tmp_path):
    make_pdf(tmp_path / "long.pdf", [f"page {i} text of the notice " * 20 for i in range(10)])
    doc = describe_document(tmp_path / "long.pdf", max_pdf_pages=8, max_text_chars=4000, excerpt_chars=300)
    assert doc.status == "long" and doc.pages == 10 and doc.image_pages == 0
    assert doc.text.startswith("page 0 text") and doc.text.endswith("[truncated]") and len(doc.text) < 330


def test_signature_only_text_layer_counts_as_scanned(tmp_path):
    make_pdf(tmp_path / "sig.pdf", ["Yours truly, For: LUCKY CEMENT LIMITED Ali Shahab Company Secretary"])
    doc = describe_document(tmp_path / "sig.pdf", 8, 4000)
    assert doc.status == "needs_ocr" and doc.pages == 1


def test_mostly_image_document_is_partial(tmp_path):
    make_pdf(tmp_path / "mixed.pdf", ["Cover letter." + BODY, "", ""])
    doc = describe_document(tmp_path / "mixed.pdf", 8, 4000)
    assert doc.status == "partial" and doc.pages == 3 and doc.image_pages == 2 and doc.text.startswith("Cover letter")


def test_long_document_that_is_mostly_images_is_still_long_with_a_note(tmp_path):
    make_pdf(tmp_path / "scan.pdf", ["Cover letter." + BODY] + [""] * 9)
    doc = describe_document(tmp_path / "scan.pdf", 8, 4000)
    assert doc.status == "long" and doc.pages == 10 and doc.image_pages == 9


def test_corrupt_pdf_is_reported_unreadable(tmp_path):
    (tmp_path / "bad.pdf").write_bytes(b"%PDF-1.4 garbage")
    assert describe_document(tmp_path / "bad.pdf", 8, 4000).status == "unreadable"


def test_pdf_cache_rejects_odd_ids(tmp_path):
    with pytest.raises(ValueError):
        PdfCache(tmp_path).path("../../etc/passwd")


# --- evidence items -----------------------------------------------------------

ROW = AnnouncementRow(date(2026, 9, 9), "9:16 AM", "ALPH", "Alpha Oil & Gas Limited", "Material Information ", "900001")


def test_item_has_stable_id_ticker_date_and_body():
    item = row_to_item(ROW, DocText("text", "First gas from the Lundali well.", 1))
    assert item.id == "ALPH-ANN-900001" and item.ticker == "ALPH" and item.date == date(2026, 9, 9)
    assert item.source == "psx_announcements" and item.type == "announcement"
    assert item.text == ("ALPH announcement on 2026-09-09 at 9:16 AM: Material Information. "
                         "Document text: First gas from the Lundali well.")


@pytest.mark.parametrize("doc, expected", [
    (DocText("needs_ocr", pages=1), "needs OCR"),
    (DocText("partial", "Cover letter.", pages=3, image_pages=2), "only 1 of 3 pages have a text layer"),
    (DocText("long", "The notice opens like this.", pages=18), "its opening reads: The notice opens like this."),
    (DocText("long", "Cover letter.", pages=10, image_pages=9), "9 of 10 pages are images"),
    (DocText("long", pages=229), "229 pages long"),
    (DocText("not_cached"), "was not downloaded"),
    (DocText("download_failed"), "could not be downloaded"),
])
def test_items_without_a_body_say_why(doc, expected):
    assert expected in row_to_item(ROW, doc).text


def test_row_without_a_document_gets_a_content_based_id():
    row = AnnouncementRow(date(2026, 7, 1), "8:30 AM", "ALPH", "Alpha", "Corporate briefing session", None)
    assert row_to_item(row, DocText("no_document")).id.startswith("ALPH-ANN-20260701-")
    assert row_to_item(row, DocText("no_document")).id == row_to_item(row, DocText("no_document")).id


# --- the fetcher (fake session and client; nothing touches the network) ---------

class FakeDps:
    """Serves list pages from a table of rows, honouring offset and count."""

    def __init__(self, rows_by_symbol, refuse=False):
        self.rows_by_symbol, self.refuse, self.calls = rows_by_symbol, refuse, []

    def post_form(self, path, data):
        self.calls.append(dict(data))
        if self.refuse:
            raise BlockedError("HTTP 403")
        rows = self.rows_by_symbol.get(data["symbol"], [])
        chunk = rows[data["offset"]:data["offset"] + data["count"]]
        body = "".join(
            f'<tr><td>{d}</td><td>{t}</td><td><a><strong>{sym}</strong></a></td><td><a><strong>Name {sym}</strong></a></td>'
            f'<td>{title} </td><td>{"<a href=/download/document/%s.pdf>PDF</a>" % doc if doc else ""}</td></tr>'
            for d, t, sym, title, doc in chunk)
        return (f'<div data-total="{len(rows)}"></div><table id="announcementsTable"><thead><tr><th>DATE</th><th>TIME</th>'
                f'<th>SYMBOL</th><th>NAME</th><th>TITLE</th><th></th></tr></thead><tbody>{body}</tbody></table>')


class FakeClient:
    def __init__(self, pdfs=None):
        self.pdfs, self.requested = pdfs or {}, []

    def get_bytes(self, url, headers=None):
        self.requested.append(url)
        doc_id = url.rsplit("/", 1)[1].removesuffix(".pdf")
        if isinstance(self.pdfs.get(doc_id), Exception):
            raise self.pdfs[doc_id]
        return self.pdfs.get(doc_id, b"<html>not a pdf</html>")


ROWS = {
    "ALPH": [("Sep 9, 2026", "9:16 AM", "ALPH", "Material Information", "900001"),
             ("Sep 4, 2026", "12:02 PM", "ALPH", "Financial results", "900002"),
             ("Aug 17, 2026", "11:53 AM", "ALPH", "Notice to shareholders", "900004"),
             ("Jul 1, 2026", "8:30 AM", "ALPH", "Corporate briefing", None)],
    "BETA": [("Sep 8, 2026", "10:00 AM", "BETA", "Appointment of director", "900010")],
}


def make_fetcher(tmp_path, live=True, dps=None, client=None, **kwargs):
    cfg = FetchConfig(live=live, cache_dir=tmp_path, min_interval_s=0)
    return AnnouncementsFetcher(cfg, date(2026, 6, 1), date(2026, 10, 12),
                                client=client or FakeClient(), session=dps or FakeDps(ROWS), **kwargs)


def good_pdfs(tmp_path):
    return {"900001": pdf_bytes(tmp_path, ["Material information: first gas from the new well." + LETTER_PAD]),
            "900002": pdf_bytes(tmp_path, ["Financial results for the year." + LETTER_PAD]),
            "900004": pdf_bytes(tmp_path, [""]),             # image-only
            "900010": pdf_bytes(tmp_path, ["Mr X appointed as director." + LETTER_PAD])}


def test_fetch_builds_items_for_each_row_with_document_text(tmp_path):
    result = make_fetcher(tmp_path / "c", client=FakeClient(good_pdfs(tmp_path))).fetch(["alph"])
    by_id = {i.id: i for i in result.items}
    assert set(by_id) == {"ALPH-ANN-900001", "ALPH-ANN-900002", "ALPH-ANN-900004"} | {
        i.id for i in result.items if i.id.startswith("ALPH-ANN-2026")}
    assert "first gas from the new well" in by_id["ALPH-ANN-900001"].text
    assert "needs OCR" in by_id["ALPH-ANN-900004"].text
    assert any("ALPH: 4 announcements" in w and "needs_ocr" in w for w in result.warnings)


def test_ticker_isolation_each_ticker_only_gets_its_own_rows(tmp_path):
    result = make_fetcher(tmp_path / "c", client=FakeClient(good_pdfs(tmp_path))).fetch(["ALPH", "BETA"])
    assert {i.ticker for i in result.items} == {"ALPH", "BETA"}
    assert [i.id for i in result.items if i.ticker == "BETA"] == ["BETA-ANN-900010"]


def test_rows_for_other_symbols_or_outside_the_window_are_dropped(tmp_path):
    rows = {"ALPH": ROWS["ALPH"][:1] + [("Sep 8, 2026", "1:00 PM", "BETA", "Wrong company", "900099"),
                                        ("Jan 5, 2026", "1:00 PM", "ALPH", "Too old", "900098")]}
    result = make_fetcher(tmp_path / "c", dps=FakeDps(rows), client=FakeClient(good_pdfs(tmp_path))).fetch(["ALPH"])
    assert [i.id for i in result.items] == ["ALPH-ANN-900001"]
    assert any("dropped a row for BETA" in w for w in result.warnings)
    assert any("outside the requested window" in w for w in result.warnings)


def test_repeated_document_is_one_item(tmp_path):
    rows = {"ALPH": [ROWS["ALPH"][0], ROWS["ALPH"][0]]}
    result = make_fetcher(tmp_path / "c", dps=FakeDps(rows), client=FakeClient(good_pdfs(tmp_path))).fetch(["ALPH"])
    assert len(result.items) == 1


def test_paging_follows_the_total_and_stops(tmp_path):
    dps = FakeDps(ROWS)
    result = make_fetcher(tmp_path / "c", dps=dps, client=FakeClient(good_pdfs(tmp_path)), page_size=3).fetch(["ALPH"])
    assert [c["offset"] for c in dps.calls] == [0, 3] and len(result.items) == 4
    assert all(c["date_from"] == "2026-06-01" and c["date_to"] == "2026-10-12" and c["type"] == "C" for c in dps.calls)


def test_page_limit_is_reported(tmp_path):
    result = make_fetcher(tmp_path / "c", client=FakeClient(good_pdfs(tmp_path)), page_size=1, max_pages=2).fetch(["ALPH"])
    assert len(result.items) == 2 and any("stopped after 2 pages" in w for w in result.warnings)


def test_no_announcements_is_a_warning_not_an_error(tmp_path):
    result = make_fetcher(tmp_path / "c").fetch(["ZZZZ"])
    assert result.items == [] and any("ZZZZ: no announcements" in w for w in result.warnings)


def test_documents_are_downloaded_once_then_read_from_cache(tmp_path):
    client = FakeClient(good_pdfs(tmp_path))
    make_fetcher(tmp_path / "c", client=client).fetch(["ALPH"])
    first = len(client.requested)
    assert first == 3                                           # three rows have a document
    make_fetcher(tmp_path / "c", client=client, dps=FakeDps({})).fetch(["ALPH"])    # fresh cache -> no list request either
    assert len(client.requested) == first


def test_offline_run_uses_only_the_cache(tmp_path):
    live = make_fetcher(tmp_path / "c", client=FakeClient(good_pdfs(tmp_path))).fetch(["ALPH"])
    dps, client = FakeDps({}), FakeClient()
    offline = make_fetcher(tmp_path / "c", live=False, dps=dps, client=client).fetch(["ALPH"])
    assert [i.id for i in offline.items] == [i.id for i in live.items]
    assert [i.text for i in offline.items] == [i.text for i in live.items]
    assert dps.calls == [] and client.requested == []


def test_offline_with_nothing_cached_is_a_cache_miss(tmp_path):
    with pytest.raises(CacheMiss):
        make_fetcher(tmp_path / "c", live=False).fetch(["ALPH"])


def test_offline_with_list_cached_but_no_pdfs_keeps_titles_and_says_so(tmp_path):
    make_fetcher(tmp_path / "c", client=FakeClient({})).fetch(["ALPH"])        # list cached; every PDF download "failed"
    shutil_target = tmp_path / "c" / "announcement_pdfs"
    assert not shutil_target.exists()
    result = make_fetcher(tmp_path / "c", live=False).fetch(["ALPH"])
    assert len(result.items) == 4 and "was not downloaded" in result.items[0].text


def test_refusal_stops_the_run(tmp_path):
    with pytest.raises(BlockedError):
        make_fetcher(tmp_path / "c", dps=FakeDps(ROWS, refuse=True)).fetch(["ALPH"])


def test_refusal_on_a_document_stops_the_run_but_other_failures_do_not(tmp_path):
    pdfs = good_pdfs(tmp_path)
    pdfs["900002"] = FetchTimeout("slow")
    result = make_fetcher(tmp_path / "c", client=FakeClient(pdfs)).fetch(["ALPH"])
    assert "could not be downloaded" in next(i for i in result.items if i.id == "ALPH-ANN-900002").text
    assert any("900002" in w and "FetchTimeout" in w for w in result.warnings)

    pdfs["900002"] = BlockedError("HTTP 403")
    with pytest.raises(BlockedError):
        make_fetcher(tmp_path / "c2", client=FakeClient(pdfs)).fetch(["ALPH"])


def test_response_that_is_not_a_pdf_is_not_cached(tmp_path):
    client = FakeClient({"900001": b"<html>login</html>"})
    result = make_fetcher(tmp_path / "c", client=client).fetch(["ALPH"])
    assert not (tmp_path / "c" / "announcement_pdfs" / "900001.pdf").exists()
    assert any("not a PDF" in w for w in result.warnings)


def test_announcements_respect_the_as_of_date(tmp_path):
    result = make_fetcher(tmp_path / "c", client=FakeClient(good_pdfs(tmp_path))).fetch(["ALPH"])
    bundle = build_bundle(result.items, "ALPH", date(2026, 8, 31))
    assert {i.id for i in bundle.items} == {"ALPH-ANN-900004"} | {i.id for i in bundle.items if i.date == date(2026, 7, 1)}
    assert all(i.date <= date(2026, 8, 31) for i in bundle.items)


def test_window_must_be_ordered():
    with pytest.raises(ValueError):
        AnnouncementsFetcher(FetchConfig(), date(2026, 10, 1), date(2026, 9, 1))


def test_long_documents_are_handed_to_the_handler_and_its_items_are_added(tmp_path):
    from mizan.schemas import EvidenceItem

    pdfs = good_pdfs(tmp_path)
    pdfs["900002"] = pdf_bytes(tmp_path, [f"page {i} text " * 20 for i in range(10)])      # 10 pages: over the limit
    seen = []

    def handler(row, path):
        seen.append((row.doc_id, path.name))
        return [EvidenceItem(f"ALPH-REPORT-{row.doc_id}-p001-0", "ALPH", "psx_report", "report_section", row.day, "chunk")]

    result = make_fetcher(tmp_path / "c", client=FakeClient(pdfs), long_document_handler=handler).fetch(["ALPH"])
    assert seen == [("900002", "900002.pdf")]
    ids = {i.id for i in result.items}
    assert "ALPH-REPORT-900002-p001-0" in ids and "ALPH-ANN-900002" in ids           # the announcement itself stays
    assert "10 pages long" in next(i for i in result.items if i.id == "ALPH-ANN-900002").text
    assert any("report 900002" in w and "1 narrative chunks" in w for w in result.warnings)


def test_without_a_handler_long_documents_only_keep_their_title(tmp_path):
    pdfs = good_pdfs(tmp_path)
    pdfs["900002"] = pdf_bytes(tmp_path, [f"page {i} text " * 20 for i in range(10)])
    result = make_fetcher(tmp_path / "c", client=FakeClient(pdfs)).fetch(["ALPH"])
    assert not any(i.type == "report_section" for i in result.items)


def test_long_periodic_report_does_not_inline_its_opening():
    row = AnnouncementRow(date(2026, 9, 25), "2:57 PM", "ALPH", "Alpha", "Transmission of Annual Report for the Year", "900003")
    text = row_to_item(row, DocText("long", "Cover page text.", pages=229)).text
    assert "229 pages long and is not included here" in text and "Cover page text" not in text
