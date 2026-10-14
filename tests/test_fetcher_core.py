from datetime import datetime, timedelta, timezone

import pytest
import requests

from mizan.fetcher.cache import PageCache, load_page
from mizan.fetcher.client import PoliteClient
from mizan.fetcher.config import FetchConfig
from mizan.fetcher.errors import (
    BlockedError,
    CacheMiss,
    FetchError,
    FetchTimeout,
    LiveFetchDisabled,
    NotFoundError,
    ServerError,
    StructureChangedError,
)

URL = "https://example.invalid/page"


class FakeResponse:
    def __init__(self, status_code=200, text="ok"):
        self.status_code, self.text = status_code, text


class FakeSession:
    """Returns/raises the queued outcomes in order and records every call."""

    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def get(self, url, headers, timeout):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeTime:
    def __init__(self):
        self.now, self.sleeps = 1000.0, []

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def clock(self):
        return self.now


def make_client(*outcomes, **config):
    t = FakeTime()
    cfg = FetchConfig(live=True, min_interval_s=5, backoff_s=2, max_retries=3, **config)
    session = FakeSession(*outcomes)
    return PoliteClient(cfg, session=session, sleep=t.sleep, clock=t.clock), session, t


# --- client -----------------------------------------------------------------

def test_live_off_never_touches_the_session():
    session = FakeSession()
    client = PoliteClient(FetchConfig(live=False), session=session)
    with pytest.raises(LiveFetchDisabled):
        client.get_text(URL)
    assert session.calls == []


def test_sends_project_user_agent_and_timeout():
    client, session, _ = make_client(FakeResponse(200, "hello"))
    assert client.get_text(URL) == "hello"
    assert "MizanFYP" in session.calls[0]["headers"]["User-Agent"]
    assert session.calls[0]["timeout"] == 30.0


def test_rate_limit_spaces_requests():
    client, _, t = make_client(FakeResponse(), FakeResponse())
    client.get_text(URL)
    t.now += 1.0                      # only 1 s passes by itself
    client.get_text(URL)
    assert t.sleeps == [4.0]          # waits the remaining 4 of 5 seconds


def test_retries_5xx_with_exponential_backoff_then_succeeds():
    client, session, t = make_client(FakeResponse(503), FakeResponse(500), FakeResponse(200, "done"))
    assert client.get_text(URL) == "done"
    assert len(session.calls) == 3
    assert [s for s in t.sleeps if s in (2, 4)] == [2, 4]   # backoff 2 s then 4 s


def test_gives_up_with_server_error_after_all_retries():
    client, session, _ = make_client(*[FakeResponse(502)] * 4)
    with pytest.raises(ServerError):
        client.get_text(URL)
    assert len(session.calls) == 4    # first try + 3 retries


def test_timeout_every_time_raises_fetch_timeout():
    client, _, _ = make_client(*[requests.Timeout()] * 4)
    with pytest.raises(FetchTimeout):
        client.get_text(URL)


def test_connection_error_is_retried_then_reported():
    client, session, _ = make_client(requests.ConnectionError("dns"), FakeResponse(200, "ok"))
    assert client.get_text(URL) == "ok"
    assert len(session.calls) == 2


@pytest.mark.parametrize("status", [401, 403])
def test_blocked_is_not_retried(status):
    client, session, _ = make_client(FakeResponse(status))
    with pytest.raises(BlockedError):
        client.get_text(URL)
    assert len(session.calls) == 1


def test_404_is_not_retried():
    client, session, _ = make_client(FakeResponse(404))
    with pytest.raises(NotFoundError):
        client.get_text(URL)
    assert len(session.calls) == 1


def test_429_retries_then_reports_blocked():
    client, session, _ = make_client(*[FakeResponse(429)] * 4)
    with pytest.raises(BlockedError):
        client.get_text(URL)
    assert len(session.calls) == 4


def test_other_4xx_is_a_plain_fetch_error():
    client, _, _ = make_client(FakeResponse(418))
    with pytest.raises(FetchError):
        client.get_text(URL)


# --- cache ------------------------------------------------------------------

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def loader(tmp_path, client, validate=lambda text: None, now=NOW, **config):
    cfg = client.config if not config else FetchConfig(live=True, **config)
    cache = PageCache(tmp_path)
    return cache, (lambda: load_page("results", URL, cfg, client, cache, validate, now=now))


def test_offline_with_empty_cache_raises_cache_miss(tmp_path):
    client = PoliteClient(FetchConfig(live=False), session=FakeSession())
    _, load = loader(tmp_path, client)
    with pytest.raises(CacheMiss):
        load()


def test_offline_uses_cached_copy_even_if_old(tmp_path):
    cache = PageCache(tmp_path)
    cache.put("results", "old page", URL, NOW - timedelta(days=90))
    session = FakeSession()
    client = PoliteClient(FetchConfig(live=False), session=session)
    page, warning = load_page("results", URL, client.config, client, cache, lambda t: None, now=NOW)
    assert page.text == "old page" and warning is None and session.calls == []


def test_live_fetches_validates_and_caches(tmp_path):
    client, session, _ = make_client(FakeResponse(200, "fresh page"))
    cache, load = loader(tmp_path, client)
    page, warning = load()
    assert page.text == "fresh page" and warning is None
    assert cache.latest("results").text == "fresh page"
    assert (page.path.with_suffix(".json")).exists()


def test_live_with_fresh_cache_makes_no_request(tmp_path):
    client, session, _ = make_client()
    cache, load = loader(tmp_path, client)
    cache.put("results", "cached", URL, NOW - timedelta(hours=2))
    page, _ = load()
    assert page.text == "cached" and session.calls == []


def test_stale_cache_is_refreshed_and_old_copy_kept(tmp_path):
    client, _, _ = make_client(FakeResponse(200, "new"))
    cache, load = loader(tmp_path, client)
    cache.put("results", "old", URL, NOW - timedelta(days=2))
    page, _ = load()
    assert page.text == "new"
    assert len(list((tmp_path / "results").glob("*.html"))) == 2   # old copy not overwritten


def test_failed_refresh_falls_back_to_cache_with_warning(tmp_path):
    client, _, _ = make_client(FakeResponse(403))
    cache, load = loader(tmp_path, client)
    cache.put("results", "old", URL, NOW - timedelta(days=2))
    page, warning = load()
    assert page.text == "old"
    assert "BlockedError" in warning and "using cached copy" in warning


def test_failed_fetch_with_no_cache_raises(tmp_path):
    client, _, _ = make_client(FakeResponse(403))
    _, load = loader(tmp_path, client)
    with pytest.raises(BlockedError):
        load()


def test_page_that_fails_validation_is_not_cached(tmp_path):
    def reject(text):
        raise StructureChangedError("table gone")

    client, _, _ = make_client(FakeResponse(200, "<html>redesigned</html>"))
    cache, load = loader(tmp_path, client, validate=reject)
    with pytest.raises(StructureChangedError):
        load()
    assert cache.latest("results") is None
