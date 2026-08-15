"""Shared HTTP layer: session, per-host pacing, retry with Retry-After backoff."""

import threading
import time
from urllib.parse import urlparse

import requests

from .. import config


class SourceError(Exception):
    def __init__(self, source: str, detail: str):
        super().__init__(f"{source}: {detail}")
        self.source = source
        self.detail = detail


_HOST_INTERVALS = {
    "api.semanticscholar.org": 1.1,
    "export.arxiv.org": 3.0,
    "api.openalex.org": 0.12,
    "api.crossref.org": 0.05,
}
_RETRY_STATUSES = {429, 500, 502, 503}
_MAX_TRIES = 3
_MAX_RETRY_AFTER = 30.0

_lock = threading.Lock()
_session: requests.Session | None = None
_session_gen = -1
_next_slot: dict[str, float] = {}


def session() -> requests.Session:
    global _session, _session_gen
    with _lock:
        gen = config.generation()
        if _session is None or _session_gen != gen:
            from hallubib import __version__

            cfg = config.get_config()
            s = requests.Session()
            ua = f"hallubib/{__version__} (https://github.com/endremborza/hallubib"
            if cfg.mailto:
                ua += f"; mailto:{cfg.mailto}"
            s.headers["User-Agent"] = ua + ")"
            _session = s
            _session_gen = gen
        return _session


def _pace(host: str) -> None:
    interval = _HOST_INTERVALS.get(host, 0.0)
    if interval <= 0:
        return
    with _lock:
        now = time.monotonic()
        slot = max(_next_slot.get(host, now), now)
        _next_slot[host] = slot + interval
    wait = slot - time.monotonic()
    if wait > 0:
        time.sleep(wait)


def _retry_delay(r: requests.Response, attempt: int) -> float | None:
    """How long to wait before retrying, or None when the server has asked for
    longer than we are willing to hold the caller for. An exhausted daily quota
    comes back as a Retry-After measured in hours; sleeping through it is not an
    option and retrying only spends more of it."""
    ra = r.headers.get("Retry-After")
    if ra:
        try:
            wait = float(ra)
        except ValueError:
            return float(2**attempt)
        return wait if wait <= _MAX_RETRY_AFTER else None
    return float(2**attempt)


def request(
    source: str,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    method: str = "GET",
    allow_redirects: bool = True,
) -> requests.Response:
    host = urlparse(url).netloc
    cfg = config.get_config()
    timeout = cfg.timeout
    if source == "openalex" and cfg.openalex_api_key:
        params = {**(params or {}), "api_key": cfg.openalex_api_key}
    detail = "request failed"
    for attempt in range(_MAX_TRIES):
        _pace(host)
        try:
            r = session().request(
                method,
                url,
                params=params,
                headers=headers,
                timeout=timeout,
                allow_redirects=allow_redirects,
            )
        except requests.RequestException as e:
            detail = str(e) or type(e).__name__
            if attempt < _MAX_TRIES - 1:
                time.sleep(float(attempt + 1))
            continue
        if r.status_code in _RETRY_STATUSES:
            detail = f"HTTP {r.status_code}"
            delay = _retry_delay(r, attempt)
            if delay is None:
                raise SourceError(
                    source,
                    f"rate limited, retry after {r.headers['Retry-After']}s",
                )
            if attempt < _MAX_TRIES - 1:
                time.sleep(delay)
            continue
        return r
    raise SourceError(source, detail)
