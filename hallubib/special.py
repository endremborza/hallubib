"""Special-case handlers for URL-based references (GitHub, arXiv, etc.)."""

import re

import requests

from . import cache
from .config import get_config
from .types import Reference

_GITHUB_REPO_RE = re.compile(r"github\.com/([^/\s]+/[^/,\s]+)")
_ARXIV_RE = re.compile(r"arxiv\.org", re.IGNORECASE)

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


def validate_url(url: str, session: requests.Session) -> bool:
    ck = cache.cache_key(f"url:{url}")
    cached = cache.get("url_check", ck)
    if cached is not None:
        return cached.get("reachable", False)
    timeout = get_config().timeout
    try:
        r = session.head(url, allow_redirects=True, timeout=timeout)
        reachable = r.status_code < 400
    except requests.RequestException:
        try:
            r = session.get(url, allow_redirects=True, timeout=timeout, stream=True)
            reachable = r.status_code < 400
            r.close()
        except requests.RequestException:
            reachable = False
    cache.put("url_check", ck, {"reachable": reachable})
    return reachable


def ignorable_supplements_for(ref: Reference) -> frozenset[str]:
    if ref.url and _ARXIV_RE.search(ref.url):
        return IGNORABLE_SUPPLEMENTS["arxiv"]
    if ref.entry_kind.name == "BOOK":
        return IGNORABLE_SUPPLEMENTS["book"]
    return IGNORABLE_SUPPLEMENTS["default"]
