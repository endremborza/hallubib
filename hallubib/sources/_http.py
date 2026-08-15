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


def _retry_delay(r: requests.Response, attempt: int) -> float:
    ra = r.headers.get("Retry-After")
    if ra:
        try:
            return min(float(ra), _MAX_RETRY_AFTER)
        except ValueError:
            pass
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
    timeout = config.get_config().timeout
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
            if attempt < _MAX_TRIES - 1:
                time.sleep(_retry_delay(r, attempt))
            continue
        return r
    raise SourceError(source, detail)
