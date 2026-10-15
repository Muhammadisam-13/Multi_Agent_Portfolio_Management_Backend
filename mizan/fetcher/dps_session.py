"""Session for the dps.psx.com.pk data endpoints (decision D7, docs/decisions.md).

What the site's own page does: every HTML page embeds a request token in
`window.__ps = {..., "_k": "<token>"}`, and the page's script then sends it as an
`X-Req-Id` header on every AJAX call (`$.ajaxSetup({headers: {"X-Req-Id": ps._k}})`),
next to jQuery's `X-Requested-With: XMLHttpRequest`. This module does the same, nothing more:

  - load the announcements page, read the token the page provides;
  - send it, with the headers above and a Referer, on the list request;
  - refresh the token when it is older than TOKEN_TTL_S, and once after a refusal.

Hard limits (D7): no CAPTCHA solving or bypass, no proxies or anti-bot services, and the
User-Agent stays the project's (set by PoliteClient). A second refusal stops the run.
"""

import json
import re
import time
from typing import Callable

from mizan.fetcher.client import PoliteClient
from mizan.fetcher.errors import BlockedError, StructureChangedError

BASE = "https://dps.psx.com.pk"
TOKEN_PAGE = f"{BASE}/announcements"
TOKEN_TTL_S = 240          # PSX rotates the token roughly every 5 minutes
_PS_SCRIPT = re.compile(r"window\.__ps\s*=\s*(\{.*?\})\s*(?:;|</script>)", re.DOTALL)
_TOKEN_SHAPE = re.compile(r"^[A-Za-z0-9_-]{16,}$")


def extract_token(html: str) -> str | None:
    """The `_k` value of `window.__ps` in a PSX page, or None if absent or not token-shaped."""
    match = _PS_SCRIPT.search(html)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(1))
    except ValueError:
        return None
    token = payload.get("_k") if isinstance(payload, dict) else None
    return token if isinstance(token, str) and _TOKEN_SHAPE.fullmatch(token) else None


class DpsSession:
    def __init__(self, client: PoliteClient, clock: Callable[[], float] = time.monotonic):
        self.client = client
        self._clock = clock
        self._token: str | None = None
        self._token_at = 0.0

    def post_form(self, path: str, data: dict) -> str:
        """POST a form the way the site's script does; refresh the token once if refused."""
        url = f"{BASE}{path}"
        if self._token is None or self._clock() - self._token_at > TOKEN_TTL_S:
            self._load_token()
        try:
            return self.client.post_text(url, data, headers=self._headers())
        except BlockedError as first:
            self._load_token()          # the token may simply have expired: one fresh page load, one retry
            try:
                return self.client.post_text(url, data, headers=self._headers())
            except BlockedError as second:
                raise BlockedError(
                    f"PSX refused {path} twice, the second time with a freshly loaded page token "
                    f"({first}; {second}). Stopping: under decision D7 we do not solve or bypass CAPTCHAs, "
                    f"use proxies or anti-bot services. Record this in docs/sources-and-compliance.md."
                ) from second

    def _load_token(self) -> None:
        html = self.client.get_text(TOKEN_PAGE)
        token = extract_token(html)
        if token is None:
            raise StructureChangedError(
                f"no request token (window.__ps._k) found on {TOKEN_PAGE}; the page changed. "
                f"If the token now comes from dynamic JavaScript, D7 allows browser automation; ask the team first.")
        self._token, self._token_at = token, self._clock()

    def _headers(self) -> dict:
        return {"X-Req-Id": self._token, "X-Requested-With": "XMLHttpRequest", "Referer": TOKEN_PAGE}
