import pytest

from mizan.fetcher.dps_session import TOKEN_PAGE, TOKEN_TTL_S, DpsSession, extract_token
from mizan.fetcher.errors import BlockedError, StructureChangedError

TOKEN_A = "A" * 20 + "_aToken-1"
TOKEN_B = "B" * 20 + "_aToken-2"


def page_with(token):
    return f'<html><script>window.__ps = {{"lc":"en","tz":"Asia/Karachi","_k": "{token}","rv":"1"}};</script></html>'


class FakeClient:
    """Stands in for PoliteClient: serves token pages, records POSTs, refuses on demand."""

    def __init__(self, tokens=(TOKEN_A,), refuse=0):
        self.tokens = list(tokens)
        self.refuse = refuse
        self.gets, self.posts = [], []

    def get_text(self, url, headers=None):
        self.gets.append(url)
        return page_with(self.tokens[min(len(self.gets), len(self.tokens)) - 1])

    def post_text(self, url, data, headers=None):
        self.posts.append({"url": url, "data": data, "headers": headers})
        if self.refuse:
            self.refuse -= 1
            raise BlockedError(f"HTTP 403 from {url}")
        return "<table/>"


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


# --- token extraction ---------------------------------------------------------

def test_extract_token_reads_the_page_variable():
    assert extract_token(page_with(TOKEN_A)) == TOKEN_A


@pytest.mark.parametrize("html", [
    "<html>no script here</html>",
    '<script>window.__ps = {"lc":"en"};</script>',                       # no _k
    '<script>window.__ps = {"_k": "short"};</script>',                   # not token-shaped
    "<script>window.__ps = {not json};</script>",
])
def test_extract_token_returns_none_when_absent_or_malformed(html):
    assert extract_token(html) is None


# --- the session --------------------------------------------------------------

def test_sends_the_headers_the_pages_script_uses():
    client = FakeClient()
    DpsSession(client).post_form("/announcements", {"symbol": "ALPH"})
    sent = client.posts[0]
    assert client.gets == [TOKEN_PAGE]
    assert sent["url"] == "https://dps.psx.com.pk/announcements" and sent["data"] == {"symbol": "ALPH"}
    assert sent["headers"] == {"X-Req-Id": TOKEN_A, "X-Requested-With": "XMLHttpRequest", "Referer": TOKEN_PAGE}


def test_token_is_loaded_once_and_reused_within_its_lifetime():
    client, clock = FakeClient(), Clock()
    session = DpsSession(client, clock)
    session.post_form("/announcements", {})
    clock.now = TOKEN_TTL_S - 1
    session.post_form("/announcements", {})
    assert len(client.gets) == 1 and len(client.posts) == 2


def test_token_is_refreshed_after_it_expires():
    client, clock = FakeClient(tokens=(TOKEN_A, TOKEN_B)), Clock()
    session = DpsSession(client, clock)
    session.post_form("/announcements", {})
    clock.now = TOKEN_TTL_S + 1
    session.post_form("/announcements", {})
    assert len(client.gets) == 2
    assert [p["headers"]["X-Req-Id"] for p in client.posts] == [TOKEN_A, TOKEN_B]


def test_one_refusal_triggers_one_fresh_token_and_one_retry():
    client = FakeClient(tokens=(TOKEN_A, TOKEN_B), refuse=1)
    assert DpsSession(client).post_form("/announcements", {}) == "<table/>"
    assert len(client.gets) == 2 and len(client.posts) == 2
    assert client.posts[1]["headers"]["X-Req-Id"] == TOKEN_B


def test_second_refusal_stops_the_run_with_a_clear_message():
    client = FakeClient(tokens=(TOKEN_A, TOKEN_B), refuse=5)
    with pytest.raises(BlockedError, match="twice") as exc:
        DpsSession(client).post_form("/announcements", {})
    assert "D7" in str(exc.value) and "CAPTCHA" in str(exc.value)
    assert len(client.posts) == 2                       # no third attempt


def test_page_without_a_token_is_a_structure_change():
    class NoToken(FakeClient):
        def get_text(self, url, headers=None):
            return "<html>redesigned</html>"

    with pytest.raises(StructureChangedError, match="token"):
        DpsSession(NoToken()).post_form("/announcements", {})
