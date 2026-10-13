"""Every way a fetch can fail has its own type, so callers can tell them apart."""


class FetchError(Exception):
    """Base class: a page could not be retrieved or understood."""


class LiveFetchDisabled(FetchError):
    """A network request was needed but live fetching is switched off."""


class CacheMiss(FetchError):
    """Live fetching is off and nothing is cached for this source."""


class BlockedError(FetchError):
    """PSX refused the request (401/403) or kept rate-limiting us (429).

    Not retried on 401/403, and never worked around: see docs/sources-and-compliance.md.
    """


class NotFoundError(FetchError):
    """404: the URL no longer exists."""


class ServerError(FetchError):
    """5xx or a connection failure that persisted through all retries."""


class FetchTimeout(FetchError):
    """The request timed out on every attempt."""


class StructureChangedError(FetchError):
    """The page loaded but no longer looks like what the parser expects."""
