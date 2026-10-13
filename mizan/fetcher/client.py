"""Polite HTTP client: rate limit, identifying User-Agent, retries with backoff."""

import time
from typing import Callable

import requests

from mizan.fetcher.config import FetchConfig
from mizan.fetcher.errors import (
    BlockedError,
    FetchError,
    FetchTimeout,
    LiveFetchDisabled,
    NotFoundError,
    ServerError,
)


class PoliteClient:
    """GET pages one at a time with a minimum gap between requests.

    session, sleep and clock can be replaced so tests never touch the network
    or really wait.
    """

    def __init__(self, config: FetchConfig, session=None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        self.config = config
        self.session = session or requests.Session()
        self._sleep = sleep
        self._clock = clock
        self._last_request: float | None = None

    def get_text(self, url: str) -> str:
        if not self.config.live:
            raise LiveFetchDisabled(f"live fetching is off, refusing to request {url}")

        failure: FetchError | None = None
        for attempt in range(self.config.max_retries + 1):
            self._wait_for_turn()
            try:
                resp = self.session.get(
                    url,
                    headers={"User-Agent": self.config.user_agent},
                    timeout=self.config.timeout_s,
                )
            except requests.Timeout:
                failure = FetchTimeout(f"timed out after {self.config.timeout_s}s: {url}")
            except requests.RequestException as exc:
                failure = ServerError(f"connection failed for {url}: {exc}")
            else:
                code = resp.status_code
                if code == 200:
                    return resp.text
                if code in (401, 403):
                    raise BlockedError(f"HTTP {code} from {url}; not retrying or working around it")
                if code == 404:
                    raise NotFoundError(f"HTTP 404 from {url}")
                if code == 429:
                    failure = BlockedError(f"HTTP 429 (rate limited) from {url}")
                elif code >= 500:
                    failure = ServerError(f"HTTP {code} from {url}")
                else:
                    raise FetchError(f"unexpected HTTP {code} from {url}")

            if attempt < self.config.max_retries:
                self._sleep(self.config.backoff_s * 2 ** attempt)

        assert failure is not None
        raise failure

    def _wait_for_turn(self) -> None:
        if self._last_request is not None:
            wait = self.config.min_interval_s - (self._clock() - self._last_request)
            if wait > 0:
                self._sleep(wait)
        self._last_request = self._clock()
