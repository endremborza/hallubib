"""Special-case handlers for URL-based references (GitHub, arXiv, etc.)."""

import ipaddress
import re
import socket
from urllib.parse import urljoin, urlparse

import requests

from . import cache
from .config import get_config
from .types import Reference

_GITHUB_REPO_RE = re.compile(r"github\.com/([^/\s]+/[^/,\s]+)")
_ARXIV_RE = re.compile(r"arxiv\.org", re.IGNORECASE)
_PUBLIC_SCHEMES = frozenset({"http", "https"})
_MAX_REDIRECTS = 5

SOURCE_TYPES: list[tuple[re.Pattern[str], str]] = [
    (_GITHUB_REPO_RE, "github"),
    (_ARXIV_RE, "arxiv"),
]

IGNORABLE_SUPPLEMENTS: dict[str, frozenset[str]] = {
    "default": frozenset({"doi", "number"}),
    "arxiv": frozenset({"doi", "number", "journal"}),
    "book": frozenset({"doi", "number", "journal", "volume", "pages"}),
}


def detect_source_type(url: str | None) -> str:
    if not url:
        return "unknown"
    for pattern, name in SOURCE_TYPES:
        if pattern.search(url):
            return name
    return "website"


def is_url_only_reference(ref: Reference) -> bool:
    if not ref.url:
        return False
    if _ARXIV_RE.search(ref.url):
        return False
    return not ref.doi and not ref.journal and not ref.volume and not ref.pages


def is_public_url(url: str) -> bool:
    """Whether a URL points at a public host we are willing to fetch.

    A bibliography is untrusted input and callers may be servers, so a `\\url{}`
    entry must not be able to make the process probe its own network: only
    http(s), and only names that resolve to globally routable addresses.
    """
    parsed = urlparse(url)
    if parsed.scheme.lower() not in _PUBLIC_SCHEMES or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except (socket.gaierror, UnicodeError, ValueError):
        return False
    return bool(infos) and all(
        ipaddress.ip_address(info[4][0]).is_global for info in infos
    )


def validate_url(url: str, session: requests.Session) -> bool:
    ck = cache.cache_key(f"url:{url}")
    cached = cache.get("url_check", ck)
    if cached is not None:
        return cached.get("reachable", False)
    reachable = _reachable(url, session)
    cache.put("url_check", ck, {"reachable": reachable})
    return reachable


def _reachable(url: str, session: requests.Session) -> bool:
    """Redirects are followed by hand so every hop is re-checked — a public URL
    that 302s to localhost must not be fetched either."""
    timeout = get_config().timeout
    for _ in range(_MAX_REDIRECTS):
        if not is_public_url(url):
            return False
        try:
            r = session.head(url, allow_redirects=False, timeout=timeout)
        except requests.RequestException:
            try:
                r = session.get(
                    url, allow_redirects=False, timeout=timeout, stream=True
                )
                r.close()
            except requests.RequestException:
                return False
        location = r.headers.get("Location")
        if r.is_redirect and location:
            url = urljoin(url, location)
            continue
        return r.status_code < 400
    return False


def ignorable_supplements_for(ref: Reference) -> frozenset[str]:
    if ref.url and _ARXIV_RE.search(ref.url):
        return IGNORABLE_SUPPLEMENTS["arxiv"]
    if ref.type == "book":
        return IGNORABLE_SUPPLEMENTS["book"]
    return IGNORABLE_SUPPLEMENTS["default"]
