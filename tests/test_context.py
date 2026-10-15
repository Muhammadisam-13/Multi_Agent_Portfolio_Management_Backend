from datetime import date, timedelta

import pytest

from mizan.retrieval.bundle import build_bundle
from mizan.retrieval.context import PER_ITEM_OVERHEAD, item_cost, select_context
from mizan.schemas import EvidenceItem

AS_OF = date(2026, 9, 30)


def make_items():
    items = []
    for n in range(40):                                          # 40 daily prices
        d = AS_OF - timedelta(days=n)
        items.append(EvidenceItem(f"AAA-PRICE-{d}", "AAA", "psxdata", "price", d, f"AAA close on {d} was {100 + n} PKR."))
    items += [
        EvidenceItem("AAA-RES-1", "AAA", "psx", "financial_results", date(2026, 8, 1), "AAA results: profit up, dividend declared."),
        EvidenceItem("AAA-ANN-1", "AAA", "psx", "announcement", date(2026, 9, 20), "AAA announcement: new gas discovery at the Lundali well."),
        EvidenceItem("AAA-ANN-2", "AAA", "psx", "announcement", date(2026, 6, 2), "AAA announcement: director appointed to the board."),
        EvidenceItem("AAA-REP-1", "AAA", "psx_report", "report_section", date(2026, 8, 20), "AAA report outlook: inflation and interest rate risk."),
        EvidenceItem("BBB-ANN-1", "BBB", "psx", "announcement", date(2026, 9, 1), "BBB announcement: other company discovery."),
        EvidenceItem("AAA-FUTURE", "AAA", "psx", "announcement", date(2026, 10, 15), "AAA future announcement about a gas discovery."),
    ]
    return items


@pytest.fixture
def bundle():
    return build_bundle(make_items(), "AAA", AS_OF)


def total_cost(items, cpt=3.0):
    return sum(item_cost(i, cpt) for i in items)


def test_budget_is_never_exceeded(bundle):
    for budget in (0, 50, 120, 400, 5000):
        sel = select_context(bundle, "gas discovery", budget)
        assert sel.used_tokens <= budget and total_cost(sel.items) == sel.used_tokens


def test_everything_fits_when_the_budget_is_large(bundle):
    sel = select_context(bundle, None, 100000)
    prices = [i for i in sel.items if i.type == "price"]
    assert len(prices) == 3                                         # old daily prices are not added without a question
    assert sel.dropped == {"price": 37}
    assert {i.id for i in sel.items if i.type != "price"} == {"AAA-RES-1", "AAA-ANN-1", "AAA-ANN-2", "AAA-REP-1"}


def test_latest_prices_and_results_come_first_when_the_budget_is_tight(bundle):
    cost = lambda ids: sum(item_cost(i, 3.0) for i in bundle.items if i.id in ids)
    must = {"AAA-RES-1"} | {i.id for i in sorted((i for i in bundle.items if i.type == "price"), key=lambda i: i.date, reverse=True)[:3]}
    sel = select_context(bundle, "director board", cost(must))
    assert {i.id for i in sel.items} == must                        # no room for anything else, even a better BM25 match


def test_the_question_pulls_in_matching_old_items(bundle):
    plain = select_context(bundle, None, 250)
    asked = select_context(bundle, "director appointed board", 250)
    assert "AAA-ANN-2" in {i.id for i in asked.items}
    assert asked.used_tokens <= 250 and plain.used_tokens <= 250


def test_a_matching_old_price_row_is_included_only_when_asked_for(bundle):
    old = (AS_OF - timedelta(days=30)).isoformat()
    assert not any(old in i.id for i in select_context(bundle, None, 100000).items)
    assert any(old in i.id for i in select_context(bundle, f"close on {old}", 100000).items)


def test_no_future_or_other_ticker_items_can_appear(bundle):
    ids = {i.id for i in select_context(bundle, "gas discovery other company future", 100000).items}
    assert "AAA-FUTURE" not in ids and "BBB-ANN-1" not in ids


def test_output_is_sorted_by_date_and_deterministic(bundle):
    a, b = select_context(bundle, "gas", 600), select_context(bundle, "gas", 600)
    assert a == b
    assert [(i.date, i.id) for i in a.items] == sorted((i.date, i.id) for i in a.items)


def test_dropped_counts_add_up(bundle):
    sel = select_context(bundle, None, 150)
    assert sum(sel.dropped.values()) + len(sel.items) == len(bundle.items)


def test_zero_budget_and_empty_bundle_give_nothing(bundle):
    assert select_context(bundle, "gas", 0).items == ()
    empty = build_bundle([], "AAA", AS_OF)
    sel = select_context(empty, "gas", 1000)
    assert sel.items == () and sel.dropped == {} and sel.used_tokens == 0


def test_item_cost_includes_the_overhead():
    item = EvidenceItem("x", "AAA", "s", "price", AS_OF, "a" * 30)
    assert item_cost(item, 3.0) == 10 + PER_ITEM_OVERHEAD


def test_the_search_function_can_be_swapped():
    from mizan.retrieval import bm25

    newest = EvidenceItem("AAA-NEW", "AAA", "psx", "announcement", date(2026, 9, 20), "Board meeting notice.")
    target = EvidenceItem("AAA-OLD", "AAA", "psx", "announcement", date(2026, 6, 1), "The reserves replacement ratio was 236 percent.")
    filler = EvidenceItem("AAA-BIG", "AAA", "psx", "announcement", date(2026, 5, 1), "Another long unrelated sentence. " * 20)
    bundle = build_bundle([newest, target, filler], "AAA", AS_OF)
    budget = max(item_cost(newest, 3.0), item_cost(target, 3.0))              # room for exactly one of the two small items

    # "replaced" only matches "replacement" once words are stemmed; without a match the newest item wins
    assert [i.id for i in select_context(bundle, "replaced", budget).items] == ["AAA-OLD"]
    assert [i.id for i in select_context(bundle, "replaced", budget, search_fn=bm25.search).items] == ["AAA-NEW"]
